"""도보 경로·하루 루트 조립 tool (rollout 2b, 설계 §6.3).

- `walk_route`  = Tmap 보행자 경로(구간별 거리/시간/경로선). 임의 직선 금지(§4.3).
- `plan_day_route` = feasible 후보 + 시간창 → 하루 1코스 조립(route_orchestrator 재사용).

둘 다 **코드 소유**(사실·계산). 실패/좌표없음은 graceful(Route unavailable·None), trace.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.agent.orchestrator import movement_from_leg
from app.agent.route_orchestrator import _build_route
from app.core.trace import Trace
from app.models.recommend import Candidate, MovementInfo, StartLocation
from app.models.route import Route
from app.sources import tmap

# 좌표(위도, 경도)
Point = tuple[float, float]


async def walk_route(
    origin: Point,
    stops: list[Point],
    trace: Trace,
    sequential: bool = False,
) -> list[MovementInfo]:
    """구간별 도보 경로(Tmap). 반환 리스트는 각 leg 의 MovementInfo(거리/시간/경로선).

    sequential=False: origin→각 stop 독립 leg(A 즉시추천, 출발점 기준 개별 이동).
    sequential=True:  origin→stop1→stop2… 연쇄 leg(B 하루 동선).
    한 leg 실패는 'Route unavailable'로 graceful — 임의 직선을 그리지 않는다(§4.3).
    """
    if not stops:
        return []
    if sequential:
        pts = [origin, *stops]
        legs = [(pts[i], pts[i + 1]) for i in range(len(stops))]
    else:
        legs = [(origin, s) for s in stops]

    results = await asyncio.gather(
        *(tmap.pedestrian_route(o[0], o[1], d[0], d[1]) for o, d in legs),
        return_exceptions=True,
    )
    movements = [movement_from_leg(r if isinstance(r, dict) else None) for r in results]
    measured = sum(1 for m in movements if m.walk_minutes is not None)
    trace.step(
        "tool.walk_route",
        legs=len(movements),
        measured=measured,
        sequential=sequential,
    )
    return movements


async def plan_day_route(
    origin: StartLocation,
    stops: list[Candidate],
    start_at: datetime,
    available_minutes: int,
    trace: Trace,
) -> Route | None:
    """feasible 후보 순서 → 하루 1코스 조립(구간 도보·계획시간·상태). 창 초과면 None.

    조립 로직은 route_orchestrator._build_route(정본) 재사용 — 여기선 tool 경계·trace 만.
    """
    route = await _build_route(origin, stops, start_at, available_minutes, trace)
    trace.step(
        "tool.plan_day_route",
        stops_in=len(stops),
        built=route is not None,
        kept=len(route.stops) if route else 0,
    )
    return route
