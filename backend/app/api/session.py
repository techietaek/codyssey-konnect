"""세션 영속 라우터 (Phase 2 L1c).

로그인(익명 포함) 사용자별 현재 요청조건·선택을 저장/복원 → 연속성(FR-L2)·
재접근. user_id 는 **검증된 JWT**(get_current_user)에서만 바인딩(cross-user 차단).
라우터는 얇게 — 쿼리는 db/, 신원은 core/auth.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth import AuthUser, get_current_user
from app.core.trace import Trace
from app.db.sessions import get_session, upsert_session
from app.models.envelope import Envelope
from app.models.session import SessionState, SessionUpdate

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/session", response_model=Envelope[SessionState])
async def read_session(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Envelope[SessionState]:
    trace = Trace()
    row = await get_session(user.id)
    return Envelope.success(data=SessionState(**(row or {})), trace_id=trace.trace_id)


@router.put("/session", response_model=Envelope[SessionState])
async def write_session(
    body: SessionUpdate,
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Envelope[SessionState]:
    trace = Trace()
    # 제공된 필드만 저장(부분 갱신) → 저장 후 최신 상태 반환.
    await upsert_session(user.id, body.model_dump(exclude_unset=True))
    row = await get_session(user.id)
    return Envelope.success(data=SessionState(**(row or {})), trace_id=trace.trace_id)
