"""선호 라우터 (Phase 2 L2 · P-09 온보딩).

로그인(익명 포함) 사용자별 장기 선호를 저장/복원. user_id 는 **검증된 JWT**
(get_current_user)에서만 바인딩(cross-user 차단). 라우터는 얇게 — 쿼리는 db/,
신원은 core/auth. 걷기 선호를 수치 제한으로 바꾸지 않는다(FR-L4, context.py 참조).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import AuthUser, get_current_user
from app.core.trace import Trace
from app.db.preferences import get_preferences, upsert_preferences
from app.models.envelope import Envelope
from app.models.preferences import PreferencesUpdate, UserPreferences

router = APIRouter(prefix="/api", tags=["preferences"])


def _to_state(row: dict | None) -> UserPreferences:
    """DB 행 → 응답 모델. 행 없음 = 아직 온보딩 전(needs_onboarding=True)."""
    if not row:
        return UserPreferences(needs_onboarding=True)
    return UserPreferences(
        interests=row.get("interests") or [],
        prefer_shorter_walks=row.get("prefer_shorter_walks"),
        open_preferences=row.get("open_preferences") or [],
        onboarded_at=row.get("onboarded_at"),
        needs_onboarding=row.get("onboarded_at") is None,
    )


@router.get("/preferences", response_model=Envelope[UserPreferences])
async def read_preferences(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Envelope[UserPreferences]:
    trace = Trace()
    row = await get_preferences(user.id)
    return Envelope.success(data=_to_state(row), trace_id=trace.trace_id)


@router.put("/preferences", response_model=Envelope[UserPreferences])
async def write_preferences(
    body: PreferencesUpdate,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Envelope[UserPreferences]:
    trace = Trace()
    # 전체 치환(Save·Skip·초기화 공용). InterestCode enum → 저장용 문자열 값.
    await upsert_preferences(
        user.id,
        interests=[i.value for i in body.interests],
        prefer_shorter_walks=body.prefer_shorter_walks,
        open_preferences=body.open_preferences,
    )
    row = await get_preferences(user.id)
    return Envelope.success(data=_to_state(row), trace_id=trace.trace_id)
