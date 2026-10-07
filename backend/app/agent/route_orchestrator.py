"""B 문화루트 파이프라인 (B2 코어).

A 파이프라인의 조회·정규화·판정(_fetch_pool·_enrich)을 재사용해 **개별 실행가능 후보**를 얻고,
domain/route 로 하루 1코스(2~3 스톱)를 조립한 뒤 구간별 도보(Tmap)를 붙인다.

신뢰 경계:
- 후보 feasibility(운영중·Hard 제외)는 A와 동일 코드가 판정(사실은 코드 소유).
- 체류시간 미주장(B-T01): 루트 total 은 **도보 이동시간**만. 도보만으로 창을 넘으면 불가.
- 관심사·이동 '균형 랭킹'(FR-B4 Soft B안)은 Product 결정 후 — 지금은 거리 기반 동선.
"""

from __future__ import annotations

import asyncio

from app.agent.context import RequestContext
from app.agent.exclude_classifier import classify_excluded
from app.agent.note_parser import parse_note
from app.agent.orchestrator import _enrich, _fetch_pool
from app.core.trace import Trace
from app.domain.exclusion import select_with_exclusion
from app.domain.locations import resolve_start_coords
from app.domain.ranking import type_preference_rank
from app.domain.route import assemble_route, rollup_budget, route_name
from app.models.recommend import (
    Candidate,
    InterestCode,
    MovementInfo,
    Provenance,
    StartLocation,
    UnconfirmedFlag,
)
from app.models.route import Route, RouteData, RouteSegment, RouteStop
from app.sources import tmap

_ROUTE_POOL = 12  # feasibility 판정할 근접 후보 수(루트 조립 여유분)


async def _segment(
    from_label: str,
    flat: float,
    flng: float,
    to_label: str,
    tlat: float,
    tlng: float,
) -> tuple[RouteSegment, int | None]:
    """한 구간 도보(Tmap). (segment, walk_minutes|None). 실패는 Route unavailable(직선 위조 금지)."""
    leg = await tmap.pedestrian_route(flat, flng, tlat, tlng)
    if leg is None:
        return (
            RouteSegment(
                from_label=from_label,
                to_label=to_label,
                movement=MovementInfo(
                    display="Route unavailable", provenance=Provenance.UNCONFIRMED
                ),
            ),
            None,
        )
    wm = leg["walk_minutes"]
    return (
        RouteSegment(
            from_label=from_label,
            to_label=to_label,
            movement=MovementInfo(
                walk_minutes=wm,
                distance_m=leg["distance_m"],
                display=f"≈{wm} min walk",
                provenance=Provenance.ESTIMATE,
                path=leg["path"] or None,
            ),
        ),
        wm,
    )


async def _build_route(
    origin: StartLocation, stops: list[Candidate], available_minutes: int, trace: Trace
) -> Route | None:
    """스톱 순서에 구간 도보를 붙여 Route 구성. 도보만으로 창 초과면 None(불가)."""
    pts: list[tuple[str, float, float]] = [
        (origin.label, origin.lat, origin.lng)  # type: ignore[list-item]
    ] + [
        (s.title, s.lat, s.lng) for s in stops
    ]  # type: ignore[misc]
    segs = await asyncio.gather(
        *(
            _segment(
                pts[i][0],
                pts[i][1],
                pts[i][2],
                pts[i + 1][0],
                pts[i + 1][1],
                pts[i + 1][2],
            )
            for i in range(len(stops))
        )
    )
    segments = [s for s, _ in segs]
    known = [wm for _, wm in segs if wm is not None]
    any_unknown = len(known) != len(segs)
    total_walk = None if any_unknown else sum(known)

    # 도보 이동만으로도 가용시간을 넘으면 걷기 루트로 불가(체류 미포함이라 보수적).
    if total_walk is not None and total_walk > available_minutes:
        return None

    flags: list[UnconfirmedFlag] = []
    if any_unknown:
        flags.append(UnconfirmedFlag(text="Some walking segments couldn't be measured"))

    return Route(
        id="route-" + "-".join(s.id for s in stops),
        name=route_name(origin, stops),
        stops=[RouteStop(order=i + 1, candidate=s) for i, s in enumerate(stops)],
        segments=segments,
        total_walk_minutes=total_walk,
        walk_provenance=Provenance.ESTIMATE,
        budget_note=rollup_budget(stops),
        stay_note="Visit times are yours to plan",
        flags=flags,
    )


async def recommend_route(
    ctx: RequestContext,
    trace: Trace,
    saved_interests: list[InterestCode] | None = None,
    prefer_shorter_walks: bool | None = None,
) -> RouteData:
    lat, lng = resolve_start_coords(ctx.start_location)
    origin = StartLocation(label=ctx.start_location.label, lat=lat, lng=lng)

    pool = await _fetch_pool(lat, lng, trace)
    # 교정된 조건이 오면 그대로, 아니면 note 를 파싱(후속 교정 "exclude museums" 등 반영).
    # 관심사·이동 '균형 랭킹'은 여전히 B안 대기 — 여기선 '명시 배제'만 적용(옵션3 재사용).
    cond = ctx.conditions if ctx.conditions is not None else await parse_note(ctx.note)
    results = await asyncio.gather(
        *(_enrich(it, ctx, cond, trace) for it in pool[:_ROUTE_POOL])
    )
    valid = [(c, txt) for (c, _, _, txt) in results if c is not None]

    # [filter] 개방형 명시 배제: LLM 의미분류로 매칭 후보 제거(사실은 코드, 0건-세이프).
    exclude_ids: set[str] = set()
    if cond.exclude_concepts and valid:
        exclude_ids = await classify_excluded(
            [(c.id, txt) for c, txt in valid], cond.exclude_concepts, trace
        )
    by_id = {c.id: c for c, _ in valid}
    kept_ids, _notices, applied = select_with_exclusion(
        [c.id for c, _ in valid], exclude_ids, cond.exclude_concepts, len(valid)
    )
    feasible = [by_id[i] for i in kept_ids]
    # 관심사 우선 루트(FR-B4): 가능하면 관심사 매칭 스톱으로 코스 구성, 2개 미만이면
    # 전체 feasible 로 폴백(강제 아님 — 원하는 콘텐츠가 충분할 때만 그걸로 짠다).
    preferred = [c for c in feasible if type_preference_rank(c.type, cond) == 0]
    trace.step(
        "route_feasible",
        considered=len(results),
        feasible=len(feasible),
        preferred=len(preferred),
        excluded_pref=len(applied),
    )

    stops = assemble_route(origin, preferred) if len(preferred) >= 2 else []
    if len(stops) < 2:
        stops = assemble_route(origin, feasible)
    if len(stops) < 2:
        trace.step("route_unmet", reason="under_2_stops", feasible=len(feasible))
        return RouteData(
            routes=[],
            origin=origin,
            unmet="We couldn't build a reliable 2–3 stop route from what's open now — see individual experiences instead.",
        )

    route = await _build_route(origin, stops, ctx.available_minutes, trace)
    if route is None:
        trace.step("route_unmet", reason="over_time_budget")
        return RouteData(
            routes=[],
            origin=origin,
            unmet="The nearest open experiences don't fit your time window as one walking route — try a longer window or see individual experiences.",
        )
    trace.step(
        "route_built",
        stops=len(route.stops),
        total_walk=route.total_walk_minutes,
        route_name=route.name,
    )
    return RouteData(routes=[route], origin=origin)
