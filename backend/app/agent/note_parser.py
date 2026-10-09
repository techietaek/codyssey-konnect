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
    "(empty list / false / null). Map interests to the fixed enum values. "
    "Put interests the user likes in 'interests'. For things they do NOT want, decide "
    "the strength: a MILD dislike that maps to one of the six interest enums goes in "
    "'avoid_interests' (e.g. 'not really into performances'); a CLEAR exclusion or refusal "
    "goes in 'exclude_concepts' as a short lowercase phrase (e.g. 'no museums' -> 'museums', "
    "'skip temples' -> 'temples', 'avoid anything religious' -> 'religious sites'). "
    "exclude_concepts is open-ended and need not map to the enum. If the user names a SPECIFIC "
    "place to remove or skip (e.g. 'remove Tapgol Park', 'not the belfry', 'drop X'), put that "
    "place name in 'exclude_places' (not exclude_concepts). If the user names a specific "
    "searchable thing — a concrete activity, craft, landmark, or subject (e.g. 'calligraphy', "
    "'hanbok', 'ceramics', 'Bukchon', 'lantern festival') — also put it in 'keywords' as a short "
    "English noun (this is for search; vibe adjectives like 'quiet' stay in open_preferences). "
    "Never place the same thing "
    "in both 'interests' and an avoid/exclude field. "
    "An indoor/outdoor preference goes ONLY in 'indoor_outdoor' (and 'indoor_outdoor_strict' "
    "for exclusive wording like 'indoor only'); never put 'indoor'/'outdoor' in "
    "open_preferences or keywords. Budget is in "
    "Korean won (KRW); only fill budget if the user gave a concrete amount. Never invent "
    "prices, times, or availability.\n"
    "Examples:\n"
    "- 'quiet indoor art galleries, no temples' -> interests:[art_exhibitions], "
    "indoor_outdoor:indoor, open_preferences:['quiet'], exclude_concepts:['temples']\n"
    "- 'try calligraphy near Bukchon, but not Gyeongbokgung' -> interests:[hands_on], "
    "keywords:['calligraphy','Bukchon'], exclude_places:['Gyeongbokgung']\n"
    "- 'outdoor only, free palaces' -> interests:[palaces_historic], indoor_outdoor:outdoor, "
    "indoor_outdoor_strict:true, free_only:true"
)

_PROMPT = ChatPromptTemplate.from_messages(
    [("system", _SYSTEM), ("human", "Note: {note}")]
)


async def parse_note(note: str | None) -> ParsedConditions:
    if not note or not note.strip():
        return ParsedConditions()
    try:
        llm = ChatOpenAI(
            model=settings.agent_orchestrator_model,  # 조건 추출(보조) — 경량 모델
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=20,
        )
        chain = _PROMPT | llm.with_structured_output(ParsedConditions)
        return await chain.ainvoke({"note": note.strip()})
    except Exception as e:  # noqa: BLE001 — LLM/네트워크 어떤 실패든 추천을 막지 않는다
        logger.warning("note parse failed: %s", type(e).__name__)
        return ParsedConditions()
