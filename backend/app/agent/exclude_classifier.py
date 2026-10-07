"""개방형 명시 배제 — LLM 의미분류 (옵션3, docs/agent-architecture.md §2-2a·§4).

공식 taxonomy(contenttypeid·cat3)가 "박물관" 같은 사용자 개념을 깨끗이 못 집는 한계를
보완한다. 사용자가 **명시적으로 배제**한 개방형 개념(enum 밖 포함)에 대해, 이미 조회·정규화된
후보의 공식 텍스트(이름·overview)를 LLM이 보고 "배제 개념에 매칭되나?"만 판단한다.

신뢰 경계(CLAUDE §6 · agent-architecture §3):
- LLM은 **의미 매칭(고르기)만** — 가격·시간·좌표·가용성 같은 사실은 생성하지 않는다.
- 애매하면 **유지**(배제하지 않음) — 개인화가 가용 후보를 함부로 떨어뜨리지 않게 보수적.
- 실패/네트워크 오류는 graceful(빈 집합 반환 → 아무것도 배제 안 함).
- 0건-세이프·확인시트 되돌리기는 호출부(orchestrator·프론트)에서 보장.
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.core.trace import Trace

logger = logging.getLogger("konnect.agent")


class _ExcludedItem(BaseModel):
    id: str = Field(description="The candidate id, copied exactly from the input list.")
    concept: str = Field(description="Which unwanted concept this candidate matched.")


class ExcludeDecision(BaseModel):
    excluded: list[_ExcludedItem] = Field(default_factory=list)


_SYSTEM = (
    "A traveler searching Seoul cultural experiences explicitly does NOT want anything "
    "matching these concepts: {concepts}. You are given candidate experiences with their "
    "official name and description. Decide which candidates CLEARLY match one of the "
    "unwanted concepts.\n"
    "Rules:\n"
    "- Judge by what the place actually is, from its name and description — not just a "
    "keyword in the title (e.g. 'Alive Museum' is a trick-art attraction, not a museum).\n"
    "- Only mark a candidate when it clearly matches. When unsure, do NOT mark it (keep it).\n"
    "- Do not invent facts. Return only ids that appear in the given list."
)

_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _SYSTEM), ("human", "Candidates:\n{candidates}")]
)


async def classify_excluded(
    items: list[tuple[str, str]], concepts: list[str], trace: Trace
) -> set[str]:
    """후보 (id, text) + 배제 개념 → 배제할 id 집합. 실패/빈 입력은 빈 집합(배제 없음)."""
    if not concepts or not items:
        return set()
    valid_ids = {i for i, _ in items}
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=20,
        )
        chain = _PROMPT | llm.with_structured_output(ExcludeDecision)
        payload = "\n".join(f"- id={i}: {text}" for i, text in items)
        res = await chain.ainvoke(
            {"concepts": ", ".join(concepts), "candidates": payload}
        )
        matches = [(e.id, e.concept) for e in res.excluded if e.id in valid_ids]
        excluded = {i for i, _ in matches}
        if excluded:
            trace.step(
                "exclude_filter",
                concepts=concepts,
                excluded=sorted(excluded),
                matches=matches,
            )
        return excluded
    except Exception as e:  # noqa: BLE001 — 분류 실패가 추천을 막지 않는다(배제 0건)
        logger.warning("exclude classify failed: %s", type(e).__name__)
        return set()
