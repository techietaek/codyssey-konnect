"""B 문화루트 라우터 (B2) — POST /api/route.

하루 1코스(2~3 스톱)를 구성해 반환. 입력은 즉시추천과 동일(RecommendRequest) —
날짜 포함 start_at 으로 B의 날짜·시간 창을 받는다. 얇게 유지 — 구성은 route_orchestrator.
Agent 의 PlanCultureRoute tool 과 동일 로직(여기는 직접 호출용).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.context import RequestContext
from app.agent.route_orchestrator import recommend_route
from app.core.auth import AuthUser, get_optional_user
from app.core.trace import Trace
from app.db.preferences import get_preferences
from app.domain.input_validation import validate_available_time
from app.models.envelope import Envelope
from app.models.recommend import InterestCode, RouteRequest
from app.models.route import RouteData

router = APIRouter(prefix="/api", tags=["route"])


@router.post("/route", response_model=Envelope[RouteData])
async def route(
    req: RouteRequest,
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> Envelope[RouteData]:
    trace = Trace()
    validate_available_time(req.start_at, req.end_at)

    saved_interests: list[InterestCode] | None = None
    prefer_shorter_walks: bool | None = None
    if user is not None:
        pref = await get_preferences(user.id)
        if pref:
            saved_interests = [InterestCode(i) for i in (pref.get("interests") or [])]
            prefer_shorter_walks = pref.get("prefer_shorter_walks")

    ctx = RequestContext(
        start_location=req.start_location,
        start_at=req.start_at,
        end_at=req.end_at,
        note=req.note,
        conditions=req.conditions,
    )
    # 저장 루트 다시보기(pin_titles): 저장된 스톱만 정확히 복원한다 — 넓게 재탐색해(want_more)
    # 스톱을 다시 찾고, 개수를 저장분으로 고정(max_stops)해 새 스톱을 덧붙이지 않는다.
    # 운영종료 등으로 못 찾은 스톱은 조용히 빠진다(사실 재조회가 정본 — 과거 스냅샷 아님).
    rebuilding = bool(req.pin_titles)
    data = await recommend_route(
        ctx,
        trace,
        saved_interests,
        prefer_shorter_walks,
        want_more=rebuilding,
        max_stops=len(req.pin_titles) if rebuilding else None,
        pin_titles=req.pin_titles,
    )
    return Envelope.success(data=data, trace_id=trace.trace_id)
