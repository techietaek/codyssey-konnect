"""Agent tool 스키마 (AG-1/2) — LLM 의 tool-calling 선택지.

각 모델은 '하나의 tool'이며, docstring·필드 설명이 LLM 에게 '언제·무엇으로' 부를지 알려준다.
LLM 은 **의도 라우팅 + 사용자 표현 추출**만 — 사실값(위치·시간·가격)은 여기에 담지 않는다.
실행은 agent/chat_agent.py 가 코드/공식 데이터로 수행한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnswerTravelQuestion(BaseModel):
    """Answer a general travel question about Seoul — transport, connectivity, money,
    etiquette, language, or explanations of cultural things (palaces, hanok, temples).
    Use for informational/FAQ questions, NOT for requests to find things to do now."""

    query: str = Field(
        description="The user's travel question, rephrased as a clear standalone query."
    )


class RecommendExperiences(BaseModel):
    """Recommend cultural experiences the traveler can actually do now, near their
    current location within their available time. Use when the user wants suggestions
    for what to see or do. Do NOT put facts like location, time, price, or hours here —
    those come from the app context and official data, not from you."""

    preferences: str = Field(
        default="",
        description="The user's own words about preferences or conditions (interests, "
        "budget, things to avoid or exclude). Empty string if they stated none.",
    )


class PlanCultureRoute(BaseModel):
    """Plan ONE day culture route — a walking course of 2–3 cultural stops in order — near
    the traveler within their time window. Use when the user wants an itinerary / route /
    plan / course connecting several places, rather than a flat list of separate suggestions.
    Location, date, and time come from the app context and official data, not from you.
    """

    preferences: str = Field(
        default="",
        description="The user's own words about preferences or conditions for the route "
        "(interests, budget, things to avoid). Empty string if they stated none.",
    )


# bind_tools 에 넘길 tool 목록(순서=표시 우선 아님, 단순 등록).
TOOL_SCHEMAS = [AnswerTravelQuestion, RecommendExperiences, PlanCultureRoute]
