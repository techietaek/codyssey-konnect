"""운영시간 자유텍스트 → 구조화 추출 (LLM, LangChain, A5 3단계).

목적: regex(domain/timing)가 '파싱 불가/계절·복수시설 caveat'로 UNCERTAIN 처리한
공식 운영시간 텍스트를, 방문일 기준으로 LLM이 **추출**해 fits/check 정확도를 높인다.

신뢰 기준(CLAUDE §6·PRD §6.2):
- 사실 '생성' 금지 — 텍스트에 쓰여있는 것만 추출. 모호하면 determinable=false.
- 판정은 코드(domain/timing.judge_extracted_hours)가. LLM 단독 Hard 제외 없음.
- 실패/빈 입력은 None 으로 graceful(추천을 막지 않음).
"""

from __future__ import annotations

import logging
from datetime import datetime

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.domain.timing import ExtractedHours

logger = logging.getLogger("konnect.agent")

_SYSTEM = (
    "You extract the operating hours that apply ON A SPECIFIC VISIT DATE from the "
    "official (possibly messy) operating-hours text of a Seoul cultural venue. "
    "Extract ONLY what the text explicitly states. Do NOT guess or invent times. "
    "If the text gives seasonal or facility-specific hours, pick the ones that apply "
    "to the given visit date/month. If the hours for that date cannot be determined "
    "from the text alone (e.g. 'inquire by phone', no concrete times, contradictory), "
    "set determinable=false and leave times null. Use 24-hour 'HH:MM'. "
    "Set always_open=true only if it clearly operates 24 hours / all day."
)

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", "Visit date: {date} ({weekday})\nHours text: {text}"),
    ]
)


async def parse_hours(
    raw_text: str | None, visit_dt: datetime
) -> ExtractedHours | None:
    if not raw_text or not raw_text.strip():
        return None
    try:
        llm = ChatOpenAI(
            model=settings.agent_orchestrator_model,  # 운영시간 추출(보조) — 경량 모델
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=20,
        )
        chain = _PROMPT | llm.with_structured_output(ExtractedHours)
        return await chain.ainvoke(
            {
                "date": visit_dt.date().isoformat(),
                "weekday": visit_dt.strftime("%A"),
                "text": raw_text.strip()[:600],
            }
        )
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 추천을 막지 않는다
        logger.warning("hours parse failed: %s", type(e).__name__)
        return None
