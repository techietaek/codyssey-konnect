"""자연어 note → 구조화 조건 (LLM, LangChain, A5).

PRD §5.2·FR-A4 신뢰 기준:
- 사용자가 '말한 조건만' 추출. 말하지 않은 선호는 만들어내지 않는다(추정 금지).
- LLM은 사실(가격·운영시간 등)을 생성하지 않는다 — 여기서는 '사용자 의도 구조화'만.
- 실패/빈 note 는 빈 조건으로 graceful(추천을 막지 않음).
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models.recommend import ParsedConditions

logger = logging.getLogger("konnect.agent")

_SYSTEM = (
    "You extract ONLY the conditions a traveler explicitly stated in their free-text "
    "note for a Seoul cultural-experience search. Do NOT infer, guess, or add anything "
    "they did not state. If a field is not mentioned, leave it at its default "
    "(empty list / false / null). Map interests to the fixed enum values. Budget is in "
    "Korean won (KRW); only fill budget if the user gave a concrete amount. Never invent "
    "prices, times, or availability."
)

_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _SYSTEM), ("human", "Note: {note}")]
)


async def parse_note(note: str | None) -> ParsedConditions:
    if not note or not note.strip():
        return ParsedConditions()
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=20,
        )
        chain = _PROMPT | llm.with_structured_output(ParsedConditions)
        return await chain.ainvoke({"note": note.strip()})
    except Exception as e:  # noqa: BLE001 — LLM/네트워크 어떤 실패든 추천을 막지 않는다
        logger.warning("note parse failed: %s", type(e).__name__)
        return ParsedConditions()
