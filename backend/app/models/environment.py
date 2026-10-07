"""환경(날씨·대기질) Context 계약 (PRD §6.6).

신뢰 불변식:
- 환경은 **Context(Soft)** — 운영 사실(휴관·취소)을 환경으로 추정하지 않는다(공식 API만).
- **공식 카테고리 등급만** 쓴다(강수형태 PTY·대기 khaiGrade). 임의 강수량/기온/PM 임계값 금지.
- 예보/실황 미확보는 `unknown` — adverse 아님(배너·강등 없음).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Precipitation(str, Enum):
    NONE = "none"
    RAIN = "rain"
    SNOW = "snow"
    RAIN_SNOW = "rain_snow"
    SHOWER = "shower"
    UNKNOWN = "unknown"


class AirGrade(str, Enum):
    GOOD = "good"
    MODERATE = "moderate"
    UNHEALTHY = "unhealthy"
    VERY_UNHEALTHY = "very_unhealthy"
    UNKNOWN = "unknown"


class EnvironmentContext(BaseModel):
    """추천 시점 환경 Context. 사실 판정이 아니라 '주의·우선순위' Soft 신호."""

    precipitation: Precipitation = Precipitation.UNKNOWN
    air_grade: AirGrade = AirGrade.UNKNOWN
    # 비/눈 또는 대기 나쁨↑ → 실내 우선(Soft). 특보 Hard 제외는 범위 밖(보류).
    adverse: bool = False
    # 사용자-facing 주의 문구(없으면 배너 미표시). 운영정보 아님.
    advisory: str | None = None
    temp_c: float | None = None  # 표시 보조(참고) — 판정엔 쓰지 않음
