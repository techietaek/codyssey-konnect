"""지식 답변 tool (rollout 2c, 설계 §6.3).

`answer_knowledge` = FAQ·여행정보·콘텐츠 Q&A 를 **검색된 근거 범위 안에서만** 답한다
(RAG, PRD §6.5). 사실 데이터(가격·운영시간 등)는 이 tool 이 아니라 공식 소스가 정본 —
근거 없으면 생성하지 않고 refusal(추가 확인 필요)로 내린다. retrieve.answer_question 재사용.
"""

from __future__ import annotations

from app.core.trace import Trace
from app.models.rag import RagAnswer
from app.rag.retrieve import answer_question


async def answer_knowledge(query: str, trace: Trace) -> RagAnswer:
    """질의 → pgvector 유사도 검색 → 근거 내 답변(grounded) 또는 refusal. graceful·trace."""
    trace.step("tool.answer_knowledge", query=query[:120])
    return await answer_question(query, trace)
