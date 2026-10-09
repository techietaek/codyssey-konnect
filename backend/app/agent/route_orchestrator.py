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
from datetime import datetime

from app.agent.context import RequestContext
from app.agent.environment import get_environment
from app.agent.exclude_classifier import classify_excluded
from app.agent.note_parser import parse_note
from app.agent.orchestrator import (
    _RADIUS_EXPANDED_NOTICE,
    _RADIUS_LADDER,
    _SEARCH_RADIUS_M,
    _augment_with_keywords,
    _fetch_pool,
    collect_judged,
)
from app.core.trace import Trace
from app.domain.budget import BudgetVerdict
from app.domain.conflict import conflict_notice, io_interest_conflict
from app.domain.exclusion import match_excluded_places, select_with_exclusion
from app.domain.locations import detect_location_in_text, resolve_start_coords
from app.domain.preferences_merge import (
    merge_saved_interests,
    merge_saved_open_preferences,
    merge_saved_walks,
)
from app.domain.ranking import io_rank, type_preference_rank
from app.domain.reasons import select_reasons
from app.domain.route import (
    assemble_route,
    build_schedule,
    fit_count,
    rollup_budget,
    route_checks,
    route_headline,
    route_name,
    route_status,
)
from app.domain.signals import classification_signals
from app.domain.timing import TimingVerdict
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
    origin: StartLocation,
    stops: list[Candidate],
    start_at: datetime,
    available_minutes: int,
    trace: Trace,
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
    walk_minutes = [wm for _, wm in segs]

    # 하루 동선: 시간창이 허용하는 만큼만(개수 제한 대신 시간 제한, 강제 채움 없음).
    keep = fit_count(walk_minutes, stops, available_minutes)
    if keep < 2:
        return None  # 창에 2개도 안 들어감 → 루트 불가(개별 전환)
    stops = stops[:keep]
    segments = [s for s, _ in segs][:keep]
    walk_minutes = walk_minutes[:keep]
    known = [wm for wm in walk_minutes if wm is not None]
    any_unknown = len(known) != len(walk_minutes)
    total_walk = None if any_unknown else sum(known)

    # 계획 방문시간 체인(공식 spendtime=confirmed / 유형 기준=planned) → 스톱별 도착·종료 + 전체 종료.
    schedule, finish_at = build_schedule(start_at, walk_minutes, stops)
    route_stops = [
        RouteStop(
            order=i + 1,
            candidate=s,
            visit_minutes=minutes,
            visit_provenance=prov,
            arrival_at=arr,
            depart_at=dep,
        )
        for i, (s, (arr, dep, minutes, prov)) in enumerate(zip(stops, schedule))
    ]
    all_official = all(p is Provenance.CONFIRMED for _, _, _, p in schedule)
    stay_note = (
        "Visit times are from official guidance."
        if all_official
        else "Planned visit times are estimates — adjust to your pace."
    )

    flags: list[UnconfirmedFlag] = []
    if any_unknown:
        flags.append(UnconfirmedFlag(text="Some walking segments couldn't be measured"))

    return Route(
        id="route-" + "-".join(s.id for s in stops),
        name=route_name(origin, stops),
        headline=route_headline(origin, stops),
        status=route_status(stops),
        checks=route_checks(stops),
        stops=route_stops,
        segments=segments,
        total_walk_minutes=total_walk,
        walk_provenance=Provenance.ESTIMATE,
        budget_note=rollup_budget(stops),
        stay_note=stay_note,
        finish_at=finish_at,
        flags=flags,
    )


async def recommend_route(
    ctx: RequestContext,
    trace: Trace,
    saved_interests: list[InterestCode] | None = None,
    prefer_shorter_walks: bool | None = None,
    saved_open_preferences: list[str] | None = None,
) -> RouteData:
    # [위치 우선] 프롬프트(note) 지명이 있으면 기본입력보다 우선(결정론, A 와 동일 정책).
    start_loc = detect_location_in_text(ctx.note) or ctx.start_location
    lat, lng = resolve_start_coords(start_loc)
    origin = StartLocation(label=start_loc.label, lat=lat, lng=lng)

    pool, env = await asyncio.gather(
        _fetch_pool(lat, lng, trace, ctx.start_at.date()),
        get_environment(lat, lng, trace),
    )
    # 교정된 조건이 오면 그대로, 아니면 note 를 파싱(후속 교정 "exclude museums" 등 반영).
    # 관심사·이동 '균형 랭킹'은 여전히 B안 대기 — 여기선 '명시 배제'만 적용(옵션3 재사용).
    cond = ctx.conditions if ctx.conditions is not None else await parse_note(ctx.note)
    # 저장 선호를 note 침묵 시에만 Soft 로 채운다(Request 우선, A 와 동일 정책).
    cond = merge_saved_interests(cond, saved_interests)
    cond = merge_saved_open_preferences(cond, saved_open_preferences)
    cond = merge_saved_walks(cond, prefer_shorter_walks)
    route_notices: list[str] = []  # 반경 확대·충돌 등 투명 안내(RouteData.notices)
    # [충돌 투명 안내] 실내/외 ↔ 관심사 모순이면 알린다(Option 1, A 와 동일). 챗 루프가 먼저
    # 되물으면 해소된 cond 로 들어와 충돌이 없다 — 그 외(직접 호출·누락) 경로의 안전망.
    conflicting = io_interest_conflict(cond)
    if conflicting:
        route_notices.append(conflict_notice(cond.indoor_outdoor or "", conflicting))

    # [keyword] 특정 주제 키워드 검색 결과 병합(P4, A 와 동일) — 발견 범위만 확장, 사실 불변.
    pool = await _augment_with_keywords(pool, lat, lng, _SEARCH_RADIUS_M, cond, trace)

    # [select+judge] 의미 관련도 선발(P2) + 적응형 반경(P1) — A 와 동일 정책을 공용 헬퍼로.
    # feasible 가 2개도 안 되면 반경을 넓혀 재조회(루트 'unmet' 감소, 강제 채움 아님).
    results, _hard, used_radius = await collect_judged(
        lat, lng, ctx, cond, trace, first_pool=pool, enrich_pool=_ROUTE_POOL
    )
    if used_radius > _RADIUS_LADDER[0]:
        route_notices.append(_RADIUS_EXPANDED_NOTICE)
    valid = [(c, txt) for (c, _, _, txt) in results]
    # 스톱별 Reason(코스 "왜 이 장소")용 판정 보관 — 관심사·시간·예산 근거 재사용(A와 동일).
    verdicts = {c.id: (t, b) for (c, t, b, _) in results}

    # [filter-places] 명시 장소 제외(B4): 사용자가 이름 댄 스톱 제거(재삽입 금지 — 조건이
    # 히스토리로 캐리포워드되는 한 매 재구성에서 다시 빠진다). 결정론 title 매칭.
    place_ids = match_excluded_places(
        [(c.id, c.title) for c, _ in valid], cond.exclude_places
    )
    if place_ids:
        valid = [v for v in valid if v[0].id not in place_ids]
        trace.step("exclude_places", places=cond.exclude_places, removed=len(place_ids))

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
    # 실내외 선호(문제1): 불일치 유형 강등 — ≥2 남으면 그걸로, 아니면 전체(0-safe, 제외 아님).
    io_base = [c for c in feasible if io_rank(c.type, cond) != 2]
    if len(io_base) < 2:
        io_base = feasible
    # 관심사 우선 루트(FR-B4): 가능하면 관심사 매칭 스톱으로, 부족하면 단계적 폴백.
    preferred = [c for c in io_base if type_preference_rank(c.type, cond) == 0]
    trace.step(
        "route_feasible",
        considered=len(results),
        feasible=len(feasible),
        io_base=len(io_base),
        preferred=len(preferred),
        excluded_pref=len(applied),
    )

    stops = assemble_route(origin, preferred) if len(preferred) >= 2 else []
    if len(stops) < 2:
        stops = assemble_route(origin, io_base)
    if len(stops) < 2:
        stops = assemble_route(origin, feasible)
    # 스톱별 Reason(코스 "왜 이 장소" — 관심사/시간/예산 근거). 근거 없으면 0개(강제 금지).
    # + AI 분류 근거 키워드(표시 전용, A 와 동일). 루트는 classify_places 미호출 →
    #   실내외는 유형 휴리스틱 fallback(io_verdict 없음). 사실 생성 아님·판정 불변(§6).
    for s in stops:
        t, b = verdicts.get(s.id, (TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN))
        s.reasons = select_reasons(s, cond, t, b, is_nearest=False)
        s.signals = classification_signals(s, cond)
    if len(stops) < 2:
        trace.step("route_unmet", reason="under_2_stops", feasible=len(feasible))
        return RouteData(
            routes=[],
            origin=origin,
            unmet="We couldn't build a reliable 2–3 stop route from what's open now — see individual experiences instead.",
            notices=route_notices,
            environment=env,
        )

    route = await _build_route(
        origin, stops, ctx.start_at, ctx.available_minutes, trace
    )
    if route is None:
        trace.step("route_unmet", reason="over_time_budget")
        return RouteData(
            routes=[],
            origin=origin,
            unmet="The nearest open experiences don't fit your time window as one walking route — try a longer window or see individual experiences.",
            notices=route_notices,
            environment=env,
        )
    trace.step(
        "route_built",
        stops=len(route.stops),
        total_walk=route.total_walk_minutes,
        route_name=route.name,
    )
    return RouteData(
        routes=[route], origin=origin, notices=route_notices, environment=env
    )
