"""B 문화루트 조립 — 실행가능성 우선, 결정론 코드 (FR-B4·B-T06).

여기는 '사실 위에서 어떻게 묶느냐'만 — 좌표/거리/예산 롤업/루트명. 조회·판정은 호출부가
이미 끝낸 feasible 후보를 넘긴다. 관심사·이동 '균형 랭킹'(FR-B4 Soft B안)은 Product 결정
3건(docs/soft-ranking.md §3) 확정 후 — 지금은 거리 기반 걷기 동선만.

신뢰 경계:
- 2~3 스톱, 2·3개 동등, **3개 강제 채움 금지** → walkable leg 상한(MAX_LEG_M)으로 자연 결정.
- 신뢰 조합 2개 미만이면 루트 성립 실패(호출부가 개별추천 전환, FR-B7).
- 체류시간 미주장(B-T01). 예산은 하나라도 미확인이면 루트 전체 '추가 확인 필요'.
"""

from __future__ import annotations

import math

from app.models.recommend import (
    Candidate,
    ExperienceType,
    PriceStatus,
    StartLocation,
)

# 자동 루트에 넣을 수 있는 유형: '자율 방문' 가능한 것. 고정 회차형(공연·축제)은
# 회차 미확인 시 자동 루트에서 제외(B-T01·FR-B4) — 시간충돌을 신뢰성 있게 판정 불가.
ROUTE_ELIGIBLE_TYPES = {
    ExperienceType.HISTORIC_VISIT,
    ExperienceType.EXHIBITION,
    ExperienceType.HANDS_ON,
    ExperienceType.DEFAULT,
}

# 한 구간(도보 레그) 상한(직선거리, 거친 게이트). 이보다 멀면 다음 스톱을 붙이지 않는다
# → 3개 강제 없이 2~3 스톱 자연 결정. A 검색 반경과 동일(1500m, 걷기 현실 범위).
MAX_LEG_M = 1500.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def route_eligible(cand: Candidate) -> bool:
    """자동 루트 편입 가능? 좌표 있고, 자율 방문 유형(고정 회차형 제외)."""
    return (
        cand.lat is not None
        and cand.lng is not None
        and cand.type in ROUTE_ELIGIBLE_TYPES
    )


def _greedy_from(
    seed: Candidate, pool: list[Candidate], max_stops: int
) -> list[Candidate]:
    """seed 에서 가까운 미사용 후보를 레그 상한 안에서 greedy 로 최대 max_stops 까지."""
    picked = [seed]
    rest = [c for c in pool if c.id != seed.id]
    cur = seed
    while len(picked) < max_stops and rest:
        nxt = min(rest, key=lambda c: haversine_m(cur.lat, cur.lng, c.lat, c.lng))  # type: ignore[arg-type]
        if haversine_m(cur.lat, cur.lng, nxt.lat, nxt.lng) > MAX_LEG_M:  # type: ignore[arg-type]
            break  # 너무 멀면 억지로 안 붙임(3개 강제 금지)
        picked.append(nxt)
        rest.remove(nxt)
        cur = nxt
    return picked


def _order_from_origin(
    origin: StartLocation, stops: list[Candidate]
) -> list[Candidate]:
    """시작점에서 가까운 순으로 방문 순서 확정(nearest-neighbor)."""
    if origin.lat is None or origin.lng is None:
        return stops
    remaining = list(stops)
    ordered: list[Candidate] = []
    cur_lat, cur_lng = origin.lat, origin.lng
    while remaining:
        nxt = min(remaining, key=lambda c: haversine_m(cur_lat, cur_lng, c.lat, c.lng))  # type: ignore[arg-type]
        ordered.append(nxt)
        remaining.remove(nxt)
        cur_lat, cur_lng = nxt.lat, nxt.lng  # type: ignore[assignment]
    return ordered


def assemble_route(
    origin: StartLocation,
    candidates: list[Candidate],
    *,
    min_stops: int = 2,
    max_stops: int = 3,
) -> list[Candidate]:
    """feasible 후보(거리순) → 하루 1코스(2~3 스톱, 방문 순서 확정).

    PRD FR-B4: 루트 1개·2~3 스톱(2·3 동등, 3개 강제 금지). 2개 미만이면 빈 리스트
    (루트 성립 실패 → 개별추천 전환, FR-B7·B-T06).
    """
    eligible = [c for c in candidates if route_eligible(c)]
    if len(eligible) < min_stops:
        return []
    # seed = 시작점에서 가장 가까운 feasible(없으면 거리순 첫째). 거기서 레그 상한 안
    # greedy 로 붙여 2~3 스톱. walkable 하게 안 붙으면 2개로 멈춤(3개 강제 금지).
    seed = eligible[0]
    if origin.lat is not None and origin.lng is not None:
        seed = min(
            eligible,
            key=lambda c: haversine_m(origin.lat, origin.lng, c.lat, c.lng),  # type: ignore[arg-type]
        )
    picked = _greedy_from(seed, eligible, max_stops)
    if len(picked) < min_stops:
        return []
    return _order_from_origin(origin, picked)


def rollup_budget(stops: list[Candidate]) -> str:
    """루트 예산 롤업. 하나라도 미확인이면 '추가 확인 필요'(전체 충족 주장 금지)."""
    statuses = [s.price.status if s.price else PriceStatus.UNKNOWN for s in stops]
    if any(
        st in (PriceStatus.UNKNOWN, PriceStatus.PARTIAL_OR_AMBIGUOUS) for st in statuses
    ):
        return "Total cost needs checking"
    if all(st == PriceStatus.FREE for st in statuses):
        return "All stops are free"
    return "See each stop for its price"


def route_name(origin: StartLocation, stops: list[Candidate]) -> str:
    """FR-B8: 근거 있는 짧은 이름(시작점 지역 기준). 근거 없으면 'Culture route'."""
    label = (origin.label or "").strip()
    if label and label.lower() not in ("current location", "my location"):
        return f"{label} culture walk"
    return "Culture route"
