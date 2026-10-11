"""개방형 명시 배제 선별·0건-세이프 (domain/exclusion) — 결정론 로직."""

from app.domain.exclusion import (
    lexical_excluded,
    match_excluded_places,
    select_with_exclusion,
)


def test_lexical_excluded_matches_title_word_and_plural():
    items = [
        ("a", "Statue of Admiral Yi Sun-Shin"),
        ("b", "King Sejong Statue"),
        ("c", "Gwanghwamun Gate"),
        ("d", "Sejong-ro Park"),
    ]
    out = lexical_excluded(items, ["statue"])  # 단수 개념 → statue/statues 제목 매칭
    assert out == {"a", "b"}  # 두 statue 모두(분류기가 놓쳐도 결정론으로 제외)
    assert lexical_excluded(items, ["park"]) == {"d"}


def test_lexical_excluded_skips_multiword_and_short():
    items = [("a", "Jogyesa Temple"), ("b", "Religious Center")]
    # 다단어(추상) 개념은 어휘로 판단 안 함 → LLM 분류에 맡김(빈 집합).
    assert lexical_excluded(items, ["religious sites"]) == set()
    assert lexical_excluded(items, ["no"]) == set()  # 너무 짧음


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


_PLACES = [
    ("a", "Tapgol Park"),
    ("b", "Museum Kimchikan"),
    ("c", "Bosingak Belfry"),
]


def test_match_excluded_places_exact_and_partial():
    assert match_excluded_places(_PLACES, ["Tapgol Park"]) == {"a"}
    assert match_excluded_places(_PLACES, ["belfry"]) == {"c"}  # 짧은 질의 부분일치
    assert match_excluded_places(_PLACES, ["kimchikan"]) == {"b"}  # 대소문자 무시


def test_match_excluded_places_guards():
    assert match_excluded_places(_PLACES, []) == set()
    assert match_excluded_places(_PLACES, ["xy"]) == set()  # <3 글자 무시(오매칭 방지)
    assert match_excluded_places(_PLACES, ["Gyeongbokgung"]) == set()  # 없는 장소
