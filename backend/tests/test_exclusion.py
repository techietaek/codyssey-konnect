"""개방형 명시 배제 선별·0건-세이프 (domain/exclusion) — 결정론 로직."""

from app.domain.exclusion import select_with_exclusion

_IDS = ["a", "b", "c", "d", "e", "f"]


def test_no_concepts_keeps_distance_order_capped():
    kept, notices, applied = select_with_exclusion(_IDS, set(), [], 4)
    assert kept == ["a", "b", "c", "d"]  # 거리순 상위 4
    assert notices == []
    assert applied == set()


def test_exclusion_removes_matched_and_keeps_order():
    # b·d 배제 → 남은 것에서 거리순 상위 4(대체가 자연 발생).
    kept, notices, applied = select_with_exclusion(_IDS, {"b", "d"}, ["museums"], 4)
    assert kept == ["a", "c", "e", "f"]
    assert notices == []
    assert applied == {"b", "d"}


def test_no_forced_fill_when_fewer_remain():
    kept, notices, _applied = select_with_exclusion(
        ["a", "b", "c"], {"b", "c"}, ["temples"], 4
    )
    assert kept == ["a"]  # 1개만 — 부적합으로 채우지 않음
    assert notices == []


def test_zero_safe_fallback_keeps_all_and_notifies():
    # 모든 유효 후보가 배제 대상 → 배제하지 않고 유지 + 안내(강등).
    kept, notices, applied = select_with_exclusion(
        ["a", "b"], {"a", "b"}, ["museums", "temples"], 4
    )
    assert kept == ["a", "b"]  # 0건으로 만들지 않음
    assert applied == set()  # 실제 배제 적용 안 됨
    assert len(notices) == 1
    assert "museums, temples" in notices[0]


def test_empty_pool_no_notice():
    kept, notices, _applied = select_with_exclusion([], {"x"}, ["museums"], 4)
    assert kept == []
    assert notices == []  # 후보 자체가 없으면 0건-세이프 아님
