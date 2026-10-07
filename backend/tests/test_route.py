"""B 문화루트 조립 — 결정론 로직 (domain/route). 좌표/거리/예산/이름/강제채움 금지."""

from datetime import datetime

from app.domain.route import (
    MAX_LEG_M,
    assemble_route,
    build_schedule,
    haversine_m,
    rollup_budget,
    route_checks,
    route_eligible,
    route_headline,
    route_name,
    route_status,
    visit_plan,
)
from app.models.recommend import (
    Candidate,
    ExperienceType,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
    StartLocation,
    UnconfirmedFlag,
)

_ORIGIN = StartLocation(label="Insadong", lat=37.570, lng=126.985)


def _c(cid, lat, type_=ExperienceType.HISTORIC_VISIT, price=PriceStatus.FREE):
    return Candidate(
        id=cid,
        title=cid.upper(),
        type=type_,
        status=ResultStatus.FITS,
        lat=lat,
        lng=126.985,
        price=PriceInfo(
            status=price, display=price.value, provenance=Provenance.CONFIRMED
        ),
    )


# 위도 0.001 ≈ 111m. A/B/C 는 근접(111m 간격), D 는 멀다(≈2.2km).
_A = _c("a", 37.571)
_B = _c("b", 37.572)
_C = _c("c", 37.573)
_D = _c("d", 37.590)


def test_haversine_sane():
    d = haversine_m(37.570, 126.985, 37.571, 126.985)
    assert 100 < d < 125  # ≈111m


def test_route_eligible_filters_type_and_coords():
    assert route_eligible(_A) is True
    assert route_eligible(_c("p", 37.571, type_=ExperienceType.PERFORMANCE)) is False
    no_coord = _c("n", 37.571)
    no_coord.lat = None
    assert route_eligible(no_coord) is False


def test_assemble_orders_from_origin_and_caps_3():
    route = assemble_route(_ORIGIN, [_C, _A, _B, _D])  # 입력 순서 뒤섞음 + D 먼곳
    assert [c.id for c in route] == [
        "a",
        "b",
        "c",
    ]  # 시작점서 가까운 순, 최대 3, D 제외


def test_assemble_two_stops_ok_not_forced_to_three():
    # A,B 근접 + D 멀다 → 레그 상한으로 D 안 붙음 → 2스톱(3개 강제 금지).
    route = assemble_route(_ORIGIN, [_A, _B, _D])
    assert [c.id for c in route] == ["a", "b"]


def test_assemble_fails_under_two():
    # A 만 근접, D 는 레그 상한 밖 → seed A 에 아무도 못 붙음 → 1스톱 → 실패([]).
    assert assemble_route(_ORIGIN, [_A, _D]) == []
    assert assemble_route(_ORIGIN, [_A]) == []


def test_assemble_excludes_fixed_schedule_types():
    perf = _c("p", 37.5715, type_=ExperienceType.PERFORMANCE)
    fest = _c("f", 37.5725, type_=ExperienceType.FESTIVAL_EVENT)
    # 자율 방문형(A) 하나만 route-eligible → 2개 미만 → 실패.
    assert assemble_route(_ORIGIN, [_A, perf, fest]) == []


def test_leg_cap_constant_matches_walk_radius():
    assert MAX_LEG_M == 1500.0


def test_rollup_budget():
    assert rollup_budget([_A, _B]) == "All stops are free"
    paid = _c("x", 37.571, price=PriceStatus.PAID)
    assert rollup_budget([paid, _c("y", 37.572, price=PriceStatus.PAID)]) == (
        "See each stop for its price"
    )
    unknown = _c("u", 37.571, price=PriceStatus.UNKNOWN)
    assert rollup_budget([_A, unknown]) == "Total cost needs checking"


def test_route_name():
    assert route_name(_ORIGIN, [_A, _B]) == "Insadong culture walk"
    assert route_name(StartLocation(label="Current location"), [_A]) == "Culture route"


def test_route_headline():
    assert route_headline(_ORIGIN, [_A, _B, _C]) == "3 stops from Insadong"
    assert (
        route_headline(StartLocation(label="Current location"), [_A, _B])
        == "2-stop culture route"
    )


def test_route_status_aggregate():
    fit = _c("f", 37.571)  # FITS
    check = Candidate(id="c", title="C", status=ResultStatus.CHECK_NEEDED)
    assert route_status([fit, _B]) is ResultStatus.FITS
    assert route_status([fit, check]) is ResultStatus.CHECK_NEEDED  # 하나라도 check


def test_visit_plan_official_beats_type_default():
    official = _c("o", 37.571, type_=ExperienceType.EXHIBITION)
    official.visit_minutes = 120  # 공식 spendtime
    assert visit_plan(official) == (120, Provenance.CONFIRMED)
    typed = _c("t", 37.571, type_=ExperienceType.EXHIBITION)  # 공식값 없음
    assert visit_plan(typed) == (60, Provenance.PLANNED)  # 유형 기준(전시 60분)


def test_build_schedule_chains_arrival_and_finish():
    start = datetime(2026, 10, 10, 14, 0)
    s1 = _c("s1", 37.571, type_=ExperienceType.HISTORIC_VISIT)  # 40분 planned
    s2 = _c("s2", 37.572, type_=ExperienceType.EXHIBITION)  # 60분 planned
    sched, finish = build_schedule(start, [10, 5], [s1, s2])
    a1, d1, m1, p1 = sched[0]
    a2, d2, m2, _p2 = sched[1]
    assert (a1.hour, a1.minute) == (14, 10) and (d1.hour, d1.minute) == (14, 50)
    assert m1 == 40 and p1 is Provenance.PLANNED
    assert m2 == 60
    assert (a2.hour, a2.minute) == (14, 55) and (d2.hour, d2.minute) == (15, 55)
    assert (finish.hour, finish.minute) == (15, 55)


def test_build_schedule_unknown_walk_drops_absolute_times():
    start = datetime(2026, 10, 10, 14, 0)
    sched, finish = build_schedule(start, [10, None], [_A, _B])
    assert finish is None  # 구간 미확인 → 절대 시각 못 묶음
    assert all(a is None and d is None for a, d, _, _ in sched)
    assert all(m > 0 for _, _, m, _ in sched)  # 방문 분·근거는 유지


def test_route_checks_aggregates_flags():
    s1 = Candidate(
        id="s1",
        title="Belfry",
        status=ResultStatus.CHECK_NEEDED,
        flags=[UnconfirmedFlag(text="Price needs checking")],
    )
    s2 = Candidate(id="s2", title="Park", status=ResultStatus.FITS)  # flag 없음
    checks = route_checks([s1, s2])
    assert checks == ["Price needs checking · Belfry"]
