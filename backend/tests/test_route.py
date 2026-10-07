"""B 문화루트 조립 — 결정론 로직 (domain/route). 좌표/거리/예산/이름/강제채움 금지."""

from app.domain.route import (
    MAX_LEG_M,
    assemble_route,
    haversine_m,
    rollup_budget,
    route_eligible,
    route_name,
)
from app.models.recommend import (
    Candidate,
    ExperienceType,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
    StartLocation,
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
