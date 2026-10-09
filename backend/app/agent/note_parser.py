"""자연어 note → 구조화 조건 (LLM, LangChain, A5).

PRD §5.2·FR-A4 신뢰 기준:
- 사용자가 '말한 조건만' 추출. 말하지 않은 선호는 만들어내지 않는다(추정 금지).
- LLM은 사실(가격·운영시간 등)을 생성하지 않는다 — 여기서는 '사용자 의도 구조화'만.
- 실패/빈 note 는 빈 조건으로 graceful(추천을 막지 않음).
"""

from __future__ import annotations

import logging
import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.models.recommend import ParsedConditions

logger = logging.getLogger("konnect.agent")

# '한 체험당 ≤₩30,000' = 우리 서비스의 'cheap' 기준(Product 결정). "free or cheap"은
# 무료만이 아니라 저렴함까지 포함 → budget_krw 로 매핑(free_only 아님). 결정론 안전망.
CHEAP_KRW = 30000
_CHEAP_RE = re.compile(
    r"\b(free or cheap|cheap|affordable|budget[- ]friendly|inexpensive)\b", re.IGNORECASE
)

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
    "open_preferences or keywords. "
    "If the user states a concrete finishing clock time (e.g. 'until 5pm', 'by 6', 'before "
    "16:30'), put it in 'end_time' as 'HH:MM' 24h. If the user states a concrete amount of "
    "time they have (e.g. 'I have 3 hours', '90 minutes', 'about an hour'), put the minutes in "
    "'duration_minutes'. Leave BOTH null for vague time words like 'afternoon', 'evening', "
    "'tonight', 'a while', 'some time' — do not convert vague words into a clock time or "
    "duration. Never invent a time. Budget is in "
    "Korean won (KRW); only fill budget if the user gave a concrete amount. "
    "If the user wants cheap/affordable/budget options (e.g. 'free or cheap', 'cheap', "
    "'affordable', 'budget-friendly') WITHOUT a specific amount, set budget_krw to 30000 "
    "(we treat up to ₩30,000 per experience as cheap) and leave free_only false — do NOT "
    "restrict to free only. Set free_only true ONLY for an explicit free-only request "
    "('free only', 'must be free', 'no paid experiences'). Never invent "
    "prices, times, or availability. "
    "For walking: 'shorter walks'/'less walking'/'not much walking' -> prefer_shorter_walks:true; "
    "an explicit OK with lots of walking ('long walks are fine', 'I don't mind walking a lot', "
    "'happy to walk') -> prefer_shorter_walks:false; if walking isn't mentioned, leave it null.\n"
    "Examples:\n"
    "- 'free or cheap' -> budget_krw:30000 (free_only stays false)\n"
    "- 'only free experiences' -> free_only:true\n"
    "- 'less walking please' -> prefer_shorter_walks:true\n"
    "- 'long walks are totally fine' -> prefer_shorter_walks:false\n"
    "- 'something near Insadong until 5pm' -> keywords:['Insadong'], end_time:'17:00'\n"
    "- 'I only have about 2 hours' -> duration_minutes:120\n"
    "- 'free galleries this afternoon' -> interests:[art_exhibitions], free_only:true "
    "(afternoon is vague -> no end_time/duration)\n"
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
        cond = await chain.ainvoke({"note": note.strip()})
    except Exception as e:  # noqa: BLE001 — LLM/네트워크 어떤 실패든 추천을 막지 않는다
        logger.warning("note parse failed: %s", type(e).__name__)
        cond = ParsedConditions()
    return _apply_cheap_rule(note, cond)


def _apply_cheap_rule(note: str, cond: ParsedConditions) -> ParsedConditions:
    """'free or cheap'/'cheap' = ≤₩30,000 선호(무료만 아님). 결정론 안전망 — LLM 이
    놓치거나 free_only 로 과도하게 좁혀도 교정한다. 구체 금액이 이미 있으면 건드리지 않는다."""
    if cond.budget_krw is None and _CHEAP_RE.search(note):
        return cond.model_copy(update={"budget_krw": CHEAP_KRW, "free_only": False})
    return cond
