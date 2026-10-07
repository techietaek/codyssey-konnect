"""RAG 검색 + 근거 범위 내 답변 (PRD §6.5·FR-C8).

흐름: 질문 임베딩 → pgvector 유사도 검색 → 근거 판정(임계치) →
  (근거 있음) LLM이 검색 근거 '안에서만' 답변 + citation
  (근거 없음) 생성하지 않고 refuse + 공식 경로 안내 (CLAUDE §6 신뢰 게이트)

신뢰 경계: 사실(가격·운영시간·예약)은 RAG가 만들지 않는다 — 공식 API 정본.
프롬프트와 지식베이스 모두 그런 사실 생성을 금지한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.trace import Trace
from app.models.rag import RagAnswer, RagCitation
from app.rag import store
from app.rag.embed import embed_query

logger = logging.getLogger("konnect.rag")

# 근거 판정: cosine similarity(=1-distance) 가 이 값 이상인 청크만 '근거'로 인정.
# 아래면 범위 밖 질문 → 생성하지 않고 refuse. (실측으로 조정 가능)
SIM_THRESHOLD = 0.35
RETRIEVE_LIMIT = 6  # 검색 후보 수
TOP_K = 4  # 답변 맥락으로 쓸 최대 근거 수

REFUSAL = (
    "I don't have confirmed information on that in my travel knowledge base. "
    "For details like prices, opening hours, or reservations, please check the "
    "official source for that place."
)

_SYSTEM = (
    "You are a helpful assistant for foreign travelers in Seoul. Answer the question "
    "using ONLY the context passages below. If the context does not contain the answer, "
    "say you don't have that information — do not guess or use outside knowledge. "
    "Never state specific prices, opening hours, or reservation/availability details even "
    "if asked; for those, tell the user to check the official source. Keep it concise, "
    "friendly, and in English."
)
_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _SYSTEM), ("human", "Context:\n{context}\n\nQuestion: {question}")]
)


def filter_grounded(
    scored: list[tuple[dict[str, Any], float]], threshold: float, top_k: int
) -> list[tuple[dict[str, Any], float]]:
    """유사도 임계치 이상인 근거만, 상위 top_k 유지(가까운 순). 없으면 빈 리스트 → refuse."""
    kept = [(meta, sim) for meta, sim in scored if sim >= threshold]
    kept.sort(key=lambda x: x[1], reverse=True)
    return kept[:top_k]


async def answer_question(question: str, trace: Trace) -> RagAnswer:
    if not question or not question.strip():
        return RagAnswer(answer=REFUSAL, grounded=False)

    qv = await embed_query(question.strip())
    raw = await asyncio.to_thread(store.query, qv, RETRIEVE_LIMIT)
    # vecs: (id, cosine_distance, metadata) → similarity = 1 - distance
    scored = [(meta, 1.0 - float(dist)) for (_id, dist, meta) in raw]
    grounded = filter_grounded(scored, SIM_THRESHOLD, TOP_K)
    top = max((s for _, s in scored), default=0.0)
    trace.step(
        "rag_retrieve",
        candidates=len(raw),
        grounded=len(grounded),
        top_score=round(top, 3),
    )

    if not grounded:
        trace.step("rag_refuse")
        return RagAnswer(answer=REFUSAL, grounded=False)

    context = "\n\n".join(
        f"[{m['doc_title']} · {m['section']}]\n{m['text']}" for m, _ in grounded
    )
    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
        timeout=20,
    )
    resp = await (_PROMPT | llm).ainvoke({"context": context, "question": question})
    citations = [
        RagCitation(
            source=f"{m['doc_title']} · {m['section']}", snippet=m["text"][:160]
        )
        for m, _ in grounded
    ]
    trace.step("rag_answer", citations=len(citations))
    return RagAnswer(answer=resp.content, grounded=True, citations=citations)
