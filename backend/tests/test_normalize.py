"""정규화 단위 테스트 (PRD §6.2 · 신뢰 게이트).

핵심: 요금 빈값·모호값을 free 로 매핑하지 않는다. 명시된 Free만 free.
"""

from __future__ import annotations

from app.domain.normalize import (
    english_display,
    enrich_intro,
    normalize_candidate,
    normalize_hours,
    normalize_price,
    parse_duration_min,
)
from app.models.recommend import ExperienceType, PriceStatus, Provenance


# ── 가격 정규화 (무료 추정 금지) ──
def test_price_empty_is_unknown_not_free():
    p = normalize_price("")
    assert p.status is PriceStatus.UNKNOWN
    assert p.provenance is Provenance.UNCONFIRMED
    assert p.raw is None


def test_price_explicit_free():
    p = normalize_price("Free admission")
    assert p.status is PriceStatus.FREE
    assert p.provenance is Provenance.CONFIRMED


def test_price_korean_free():
    assert normalize_price("무료").status is PriceStatus.FREE


def test_price_with_amount_is_paid():
    p = normalize_price("Adults 3,000 won / Children 1,500 won")
    assert p.status is PriceStatus.PAID
    assert p.raw == "Adults 3,000 won / Children 1,500 won"


def test_price_free_and_paid_is_partial():
    assert (
        normalize_price("Free for children, Adults 3,000 won").status
        is PriceStatus.PARTIAL_OR_AMBIGUOUS
    )


def test_price_paid_without_amount_is_unknown():
    # 유료는 확인되지만 금액 미상 → unknown(긍정으로 메우지 않음)
    p = normalize_price("Paid (inquire by phone)")
    assert p.status is PriceStatus.UNKNOWN


def test_price_vague_is_unknown():
    assert normalize_price("Varies by program").status is PriceStatus.UNKNOWN


# ── detailInfo2 보강 (enrich_intro) ──
def test_enrich_fills_empty_fee_from_info():
    intro = {"usefee": "", "usetime": "09:00-18:00"}
    info = [
        {"infoname": "Restrooms", "infotext": "Available"},
        {
            "infoname": "Admission Fees",
            "infotext": "Adults 5,000 won / Children 2,000 won",
        },
    ]
    out = enrich_intro(intro, info)
    assert normalize_price(out["usefee"]).status is PriceStatus.PAID
    assert out["usetime"] == "09:00-18:00"  # 이미 있는 값은 덮어쓰지 않음


def test_enrich_fills_free_fee_from_info():
    out = enrich_intro({}, [{"infoname": "Admission Fees", "infotext": "Free"}])
    assert normalize_price(out["usefee"]).status is PriceStatus.FREE


def test_enrich_does_not_overwrite_existing_fee():
    intro = {"usefee": "Adults 3,000 won"}
    out = enrich_intro(intro, [{"infoname": "Admission Fees", "infotext": "Free"}])
    assert out["usefee"] == "Adults 3,000 won"


def test_enrich_no_info_is_noop():
    intro = {"usefee": ""}
    assert enrich_intro(intro, []) is intro
    assert enrich_intro(intro, None) is intro


def test_enrich_ignores_non_fee_rows():
    # 요금/시간과 무관한 행만 있으면 보강하지 않음(빈값 유지 → unknown)
    out = enrich_intro({}, [{"infoname": "Available Facilities", "infotext": "Cafe"}])
    assert not out.get("usefee")


# ── 제목 정리 (한글 제거, english_display) ──
def test_english_display_strips_korean_parens():
    assert english_display("Gyeongbokgung Palace (경복궁)") == "Gyeongbokgung Palace"


def test_english_display_nested_parens():
    assert (
        english_display("Dongdaemun Design Plaza (동대문디자인플라자 (DDP))")
        == "Dongdaemun Design Plaza"
    )


def test_english_display_keeps_english_parens():
    assert english_display("Museum (Main Hall)") == "Museum (Main Hall)"


def test_english_display_strips_square_bracket_korean():
    # 사용자 보고 케이스 — 대괄호 안 한글(+중첩 소괄호) 제거.
    assert (
        english_display("Alive Museum (Insa-dong Branch) [박물관은 살아있다(인사동점)]")
        == "Alive Museum (Insa-dong Branch)"
    )


def test_english_display_strips_leading_korean_run():
    assert english_display("경복궁 Gyeongbokgung") == "Gyeongbokgung"


def test_english_display_all_korean_keeps_original():
    # 전부 한글(서울 행사 등)은 영문 이름이 없어 영문화 불가 → 원문 유지(지우지 않음).
    assert english_display("서울서예박물관") == "서울서예박물관"


def test_english_display_korean_name_with_year_keeps_original():
    # 축제명이 한글 + 연도 숫자뿐이면 '2026'으로 지우지 않고 원문(한글) 유지.
    assert english_display("서울빛초롱축제 2026") == "서울빛초롱축제 2026"
    assert english_display("2026 서울거리공연") == "2026 서울거리공연"


def test_english_display_empty():
    assert english_display(None) == ""
    assert english_display("") == ""


# ── 시간 ──
def test_hours_present_confirmed():
    t = normalize_hours({"usetime": "09:00-18:00"})
    assert t is not None and t.provenance is Provenance.CONFIRMED


def test_hours_absent_is_none():
    assert normalize_hours({}) is None


# ── 후보 조립 (좌표 검증 · flag) ──
def _item(**kw):
    base = {
        "contentid": "1",
        "contenttypeid": "78",
        "title": "Test Museum (테스트)",
        "mapx": "126.98",
        "mapy": "37.57",
        "firstimage": "",
    }
    base.update(kw)
    return base


def test_candidate_unknown_price_gets_flag():
    c = normalize_candidate(_item(), intro={}, common={})
    assert c is not None
    assert c.type is ExperienceType.EXHIBITION
    assert c.price.status is PriceStatus.UNKNOWN
    flag_texts = [f.text for f in c.flags]
    assert "Price needs checking" in flag_texts
    assert "Hours need checking" in flag_texts  # intro 비어 hours 미확인
    assert c.image_url is None  # firstimage 빈값 → None(가짜 이미지 금지)


def test_candidate_out_of_range_coords_dropped():
    assert normalize_candidate(_item(mapx="0", mapy="0"), {}, {}) is None


def test_candidate_free_no_price_flag():
    c = normalize_candidate(_item(), intro={"usefeeculture": "Free"}, common={})
    assert c.price.status is PriceStatus.FREE
    assert "Price needs checking" not in [f.text for f in c.flags]


def test_parse_duration_min():
    assert parse_duration_min("180 minutes") == 180
    assert parse_duration_min("1시간 30분") == 90
    assert parse_duration_min("About 2 hours") == 120
    assert parse_duration_min("60분") == 60
    assert parse_duration_min("") is None  # 빈값 → 추정 안 함
    assert parse_duration_min("free") is None  # 숫자 없음 → None
