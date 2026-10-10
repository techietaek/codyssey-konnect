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
from datetime import datetime, timedelta

from app.models.recommend import (
    Candidate,
    ExperienceType,
    PriceStatus,
    Provenance,
    ResultStatus,
    StartLocation,
)

_GENERIC_LABELS = ("current location", "my location", "")

# 유형 기준 표준 방문시간(분) — B-T01 허용 '유형 기준' 근거(임의 per-place 숫자 아님).
# 공식 spendtime 이 없을 때만 Planned(예상)으로 쓴다. 문서화된 유형 표준이라 근거가 명시된다.
_TYPE_VISIT_MIN = {
    ExperienceType.EXHIBITION: 60,  # 박물관·미술관 관람
    ExperienceType.HISTORIC_VISIT: 40,  # 궁·역사장소·공원 둘러보기
    ExperienceType.HANDS_ON: 90,  # 체험 참여
    ExperienceType.FESTIVAL_EVENT: 60,
    ExperienceType.PERFORMANCE: 90,
    ExperienceType.DEFAULT: 45,
}

# 자동 루트에 넣을 수 있는 유형: '자율 방문' 가능한 것. 고정 회차형(공연·축제)은
# 회차 미확인 시 자동 루트에서 제외(B-T01·FR-B4) — 시간충돌을 신뢰성 있게 판정 불가.
ROUTE_ELIGIBLE_TYPES = {
    ExperienceType.HISTORIC_VISIT,
    ExperienceType.EXHIBITION,
    ExperienceType.HANDS_ON,
    ExperienceType.DEFAULT,
}

# 한 구간(도보 레그) 상한(직선거리, 거친 게이트). 이보다 멀면 다음 스톱을 붙이지 않는다
# (걷기 현실 범위, A 검색 반경과 동일 1500m).
MAX_LEG_M = 1500.0

# 하루 코스 스톱 수 실용 상한(Product: 개수 제한 없이 '하루 동선' — 실제 제한은 시간창).
# 이건 고정 목표치가 아니라 Tmap 호출·조립을 bound 하는 안전 상한. 실제 길이는 시간이 결정.
MAX_DAY_STOPS = 8


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
    max_stops: int = MAX_DAY_STOPS,
    pinned: list[Candidate] | None = None,
) -> list[Candidate]:
    """feasible 후보(거리순) → 하루 동선(걸을 수 있는 만큼 이어붙인 체인, 방문 순서 확정).

    개수 고정 제한 없음(Product: 하루 동선) — walkable leg 상한으로 자연 종료, 실제 길이는
    호출부의 시간창 트림(fit_count)이 결정. 2개 미만이면 빈 리스트(성립 실패 → 개별 전환).

    pinned 가 오면(= '더/추가' 턴에서 직전 루트 스톱) 그 순서·구성을 고정 prefix 로 **유지**하고
    새 스톱만 마지막 고정 스톱에서 greedy 로 이어붙인다(기존 스톱 drop/reorder 금지). 전체
    재조립이 아니라 진짜 append — 사용자가 본 루트가 유지된다(working_memory 약속과 일치).
    """
    eligible = [c for c in candidates if route_eligible(c)]
    if pinned:
        # route_eligible 한 기존 스톱만 고정. 이번 턴 운영조건에서 빠진 스톱 제거는 호출부
        # (_resolve_pinned 가 feasible 교집합만 넘김)가 담당 — 여기선 좌표/유형만 방어.
        kept = [c for c in pinned if route_eligible(c)]
        if kept:
            pin_ids = {c.id for c in kept}
            rest_pool = [c for c in eligible if c.id not in pin_ids]
            budget = max_stops - len(kept)
            if budget <= 0:
                picked = kept[:max_stops]
            else:
                # kept[-1] 에서 새 스톱만 budget 개까지 이어붙임(prefix 는 그대로 보존).
                chain = _greedy_from(kept[-1], [kept[-1], *rest_pool], budget + 1)
                picked = kept + chain[1:]
            if len(picked) < min_stops:
                return []
            return picked
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


def route_headline(origin: StartLocation, stops: list[Candidate]) -> str:
    """코스 헤드라인 — "N stops from {지역}". 지역 근거 없으면 "N-stop culture route"."""
    label = (origin.label or "").strip()
    n = len(stops)
    if label.lower() not in _GENERIC_LABELS:
        return f"{n} stops from {label}"
    return f"{n}-stop culture route"


def route_status(stops: list[Candidate]) -> ResultStatus:
    """루트 전체 상태 — 모든 스톱이 fits면 FITS, 하나라도 확인필요면 CHECK_NEEDED.
    개별 사실을 덮지 않는다(각 스톱 배지는 그대로) — 코스 레벨 요약일 뿐."""
    if any(s.status is not ResultStatus.FITS for s in stops):
        return ResultStatus.CHECK_NEEDED
    return ResultStatus.FITS


def route_checks(stops: list[Candidate]) -> list[str]:
    """코스 전체에서 '가기 전 확인할 것' 집계 — 각 스톱의 미확인 flag를 '{내용} · {장소}'로."""
    checks: list[str] = []
    for s in stops:
        for f in s.flags:
            checks.append(f"{f.text} · {s.title}")
    return checks


def visit_plan(cand: Candidate) -> tuple[int, Provenance]:
    """스톱 방문 소요(분, provenance). 공식 spendtime 있으면 CONFIRMED, 없으면 유형 기준 PLANNED.
    임의 per-place 숫자가 아니라 '공식값 또는 문서화된 유형 표준'(B-T01)."""
    if cand.visit_minutes:
        return cand.visit_minutes, Provenance.CONFIRMED
    return _TYPE_VISIT_MIN.get(cand.type, _TYPE_VISIT_MIN[ExperienceType.DEFAULT]), (
        Provenance.PLANNED
    )


def fit_count(
    walk_minutes: list[int | None], stops: list[Candidate], available_minutes: int
) -> int:
    """시간창에 맞는 최장 스톱 수 — 도보+방문 누적이 available_minutes 를 넘지 않는 선까지.

    하루 동선을 '시간이 허용하는 만큼' 채운다(개수 제한 대신 시간 제한). 강제 채움 아님 —
    다음 스톱이 창을 넘으면 멈춘다. 도보 미확인 구간을 만나면 그 이후는 시각을 못 묶어 중단.
    """
    elapsed = 0
    keep = 0
    for i, s in enumerate(stops):
        w = walk_minutes[i] if i < len(walk_minutes) else None
        if w is None:
            break
        minutes, _ = visit_plan(s)
        elapsed += w + minutes
        if elapsed <= available_minutes:
            keep = i + 1
        else:
            break
    return keep


def build_schedule(
    start_at: datetime, walk_minutes: list[int | None], stops: list[Candidate]
) -> tuple[
    list[tuple[datetime | None, datetime | None, int, Provenance]], datetime | None
]:
    """start_at + 구간 도보분 + 스톱 방문분을 체인 → 스톱별 (arrival, depart, 분, provenance)와
    전체 종료(finish). 구간 도보가 하나라도 미확인이면 절대 시각은 못 묶으므로 arrival/depart=None
    (방문 분·근거는 그대로 반환), finish=None. 임의 직선·추정 시각 위조 금지와 같은 선상."""
    plans = [visit_plan(s) for s in stops]
    if any(w is None for w in walk_minutes):
        return [(None, None, m, p) for (m, p) in plans], None
    clock = start_at
    out: list[tuple[datetime | None, datetime | None, int, Provenance]] = []
    for i, (minutes, prov) in enumerate(plans):
        clock += timedelta(minutes=walk_minutes[i] or 0)
        arrival = clock
        clock += timedelta(minutes=minutes)
        out.append((arrival, clock, minutes, prov))
    return out, clock
