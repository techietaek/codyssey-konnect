"""즉시 추천(A) 파이프라인 (A2: 조회→정규화).

structure → fetch(공식 API) → compose(정규화·소수 후보). 판정(A3)·Reason(A5)은 이후.
한 소스 실패가 전체 실패로 번지지 않게 부분 실패를 허용한다(CLAUDE §4.2).
LLM은 아직 쓰지 않는다 — 조회·정규화는 코드로.
"""

from __future__ import annotations

import asyncio

from app.agent.context import RequestContext
from app.core.exceptions import ExternalSourceError
from app.core.trace import Trace
from app.domain.curation import is_cultural_experience
from app.domain.locations import resolve_start_coords
from app.domain.normalize import normalize_candidate
from app.domain.status import resolve_status
from app.domain.timing import judge_timing
from app.models.recommend import (
    Candidate,
    MovementInfo,
    Provenance,
    RecommendData,
    StartLocation,
)
from app.sources import tmap, tourapi

# 문화경험 콘텐츠 타입(EngService2): 관광지·문화시설·축제/공연/행사.
# (식당·쇼핑·숙박 등은 제외 — PRD §6.4)
_CULTURAL_TYPES = (76, 78, 85)
_SEARCH_RADIUS_M = 1500
_MAX_CANDIDATES = 4
_ENRICH_POOL = 8  # 판정 후 Hard 제외분을 다음 후보로 대체하기 위한 보강 범위


async def _fetch_pool(lat: float, lng: float, trace: Trace) -> list[dict]:
    """문화 타입별 목록을 병렬 조회 → 병합·중복제거·거리순. 전부 실패 시 예외."""
    results = await asyncio.gather(
        *(
            tourapi.location_based_list(lat, lng, _SEARCH_RADIUS_M, t)
            for t in _CULTURAL_TYPES
        ),
        return_exceptions=True,
    )
    ok_lists = [r for r in results if not isinstance(r, Exception)]
    failed = len(results) - len(ok_lists)
    if not ok_lists:
        raise ExternalSourceError("TourAPI unavailable for all cultural types")

    # 문화경험이 아닌 카테고리(의료관광·관광거리·안내소·음식거리 등)를 제외한다.
    # 판단은 domain/curation 으로 분리(PRD §6.4, 테스트 가능).
    merged: dict[str, dict] = {}
    for items in ok_lists:
        for it in items:
            cid = it.get("contentid")
            if cid and cid not in merged and is_cultural_experience(it):
                merged[cid] = it

    def _dist(it: dict) -> float:
        try:
            return float(it.get("dist") or 1e12)
        except ValueError:
            return 1e12

    pool = sorted(merged.values(), key=_dist)
    trace.step("fetch", pool=len(pool), sources_failed=failed)
    return pool


async def _enrich(item: dict, ctx: RequestContext) -> tuple[Candidate | None, str]:
    """상세 조회→정규화→판정. Hard 충돌(영업외·휴무)은 (None, 사유)로 제외."""
    cid = str(item.get("contentid"))
    ctype = str(item.get("contenttypeid"))
    intro, common = await asyncio.gather(
        tourapi.detail_intro(cid, ctype),
        tourapi.detail_common(cid),
        return_exceptions=True,
    )
    intro = intro if isinstance(intro, dict) else {}
    common = common if isinstance(common, dict) else {}

    cand = normalize_candidate(item, intro, common)
    if cand is None:
        return None, "invalid/out-of-range data"

    # [judge] 운영시간·휴무 → 3상태. Hard 충돌은 제외(정상 추천에서 뺀다).
    verdict, reason = judge_timing(intro, ctx.start_at, ctx.end_at)
    status, flags = resolve_status(cand, verdict)
    if status is None:
        return None, reason  # Hard 제외
    cand.status = status
    cand.flags = flags
    return cand, reason


async def _attach_movement(cand: Candidate, olat: float, olng: float) -> None:
    """후보에 도보 이동정보(Tmap) 부착. 실패/좌표없음 → Route unavailable(직선 위조 금지)."""
    route = None
    if cand.lat is not None and cand.lng is not None:
        route = await tmap.pedestrian_route(olat, olng, cand.lat, cand.lng)
    if route is None:
        cand.movement = MovementInfo(
            display="Route unavailable", provenance=Provenance.UNCONFIRMED
        )
        return
    wm = route["walk_minutes"]
    cand.movement = MovementInfo(
        walk_minutes=wm,
        distance_m=route["distance_m"],
        display=f"≈{wm} min walk",
        provenance=Provenance.ESTIMATE,  # 예상값 — 실제 ETA 보장 아님
        path=route["path"] or None,
    )


async def recommend_a(ctx: RequestContext, trace: Trace) -> RecommendData:
    lat, lng = resolve_start_coords(ctx.start_location)
    trace.step(
        "structure",
        start=ctx.start_location.label,
        coords=f"{lat:.4f},{lng:.4f}",
        available_minutes=ctx.available_minutes,
    )

    pool = await _fetch_pool(lat, lng, trace)

    # 가까운 순 넉넉히 보강·판정 후 '유효한' 소수만 유지(제외분을 다음 후보로 대체.
    # 부적합 후보로 숫자 채우는 것 아님 — 유효 후보 중 가까운 순 최대 4개).
    results = await asyncio.gather(*(_enrich(it, ctx) for it in pool[:_ENRICH_POOL]))
    candidates: list[Candidate] = []
    excluded = 0
    for cand, _reason in results:
        if cand is None:
            excluded += 1
        elif len(candidates) < _MAX_CANDIDATES:
            candidates.append(cand)

    fits = sum(1 for c in candidates if c.status.value == "fits")
    trace.step(
        "judge",
        considered=len(results),
        excluded_hard=excluded,
        fits=fits,
        check_needed=len(candidates) - fits,
    )

    # [route] 후보별 도보 이동정보(Tmap) 병렬 부착
    await asyncio.gather(*(_attach_movement(c, lat, lng) for c in candidates))
    with_path = sum(1 for c in candidates if c.movement and c.movement.path)
    trace.step("route", with_path=with_path, total=len(candidates))

    trace.step("compose", kept=len(candidates))
    origin = StartLocation(label=ctx.start_location.label, lat=lat, lng=lng)
    return RecommendData(candidates=candidates, origin=origin)
