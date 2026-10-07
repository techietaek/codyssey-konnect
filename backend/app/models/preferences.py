"""장기 사용자 선호 입출력 스키마 (Phase 2 L2 · P-09 온보딩).

신뢰 불변식(CLAUDE §6 / FR-L4·L5):
- 걷기 선호(prefer_shorter_walks)는 **Soft ranking signal only** — 분·km·Hard 상한으로
  변환하지 않는다. NULL(미선택)을 긍정/부정 기본값으로 바꾸지 않는다.
- 저장 선호는 현재 Request·사실·필수 조건을 덮어쓰지 않는다(병합은 context.py).
- 관심사는 InterestCode 6개로만 제한(RAG·note 파싱과 동일 enum 재사용).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.recommend import InterestCode


class UserPreferences(BaseModel):
    """저장된 선호(GET 응답).

    needs_onboarding: 아직 P-09 를 한 번도 보지 않음(onboarded_at 부재) → 최초 1회만 노출.
    Skip 해도 저장 시 onboarded_at 을 찍어 재노출을 막는다(FR-L3 '반복 노출 금지').
    """

    interests: list[InterestCode] = Field(default_factory=list)
    prefer_shorter_walks: bool | None = None
    onboarded_at: str | None = None
    needs_onboarding: bool = True


class PreferencesUpdate(BaseModel):
    """선호 저장/수정/초기화(PUT 본문). 온보딩 Save·Skip·My Page 수정 공용.

    - Skip: 빈 interests + prefer_shorter_walks=None 으로 저장(온보딩 노출만 종료).
    - 초기화(L3): interests=[] + prefer_shorter_walks=None 으로 동일 PUT.
    어느 경우든 저장 시 onboarded_at 을 갱신한다(db 레이어).
    """

    interests: list[InterestCode] = Field(default_factory=list)
    prefer_shorter_walks: bool | None = None
