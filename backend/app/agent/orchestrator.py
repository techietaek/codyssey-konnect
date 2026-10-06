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
from app.models.recommend import Candidate
from app.sources import tourapi

# 문화경험 콘텐츠 타입(EngService2): 관광지·문화시설·축제/공연/행사.
# (식당·쇼핑·숙박 등은 제외 — PRD §6.4)
_CULTURAL_TYPES = (76, 78, 85)
_SEARCH_RADIUS_M = 1500
_MAX_CANDIDATES = 4


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


async def _enrich(item: dict) -> Candidate | None:
    """후보 1개 상세 조회(intro·common 병렬) 후 정규화. 상세 실패는 미확인으로 둠."""
    cid = str(item.get("contentid"))
    ctype = str(item.get("contenttypeid"))
    intro, common = await asyncio.gather(
        tourapi.detail_intro(cid, ctype),
        tourapi.detail_common(cid),
        return_exceptions=True,
    )
    intro = intro if isinstance(intro, dict) else {}
    common = common if isinstance(common, dict) else {}
    return normalize_candidate(item, intro, common)


async def recommend_a(ctx: RequestContext, trace: Trace) -> list[Candidate]:
    lat, lng = resolve_start_coords(ctx.start_location)
    trace.step(
        "structure",
        start=ctx.start_location.label,
        coords=f"{lat:.4f},{lng:.4f}",
        available_minutes=ctx.available_minutes,
    )

    pool = await _fetch_pool(lat, lng, trace)

    # 가까운 순으로 소수만 상세 조회·정규화(강제 채움 금지: 최대 4개)
    enriched = await asyncio.gather(*(_enrich(it) for it in pool[:_MAX_CANDIDATES]))
    candidates = [c for c in enriched if c is not None]
    trace.step("compose", kept=len(candidates))
    return candidates
