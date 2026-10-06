"""정규화 단위 테스트 (PRD §6.2 · 신뢰 게이트).

핵심: 요금 빈값·모호값을 free 로 매핑하지 않는다. 명시된 Free만 free.
"""

from __future__ import annotations

from app.domain.normalize import (
    _clean_title,
    normalize_candidate,
    normalize_hours,
    normalize_price,
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


# ── 제목 정리 ──
def test_clean_title_strips_korean_parens():
    assert _clean_title("Gyeongbokgung Palace (경복궁)") == "Gyeongbokgung Palace"


def test_clean_title_nested_parens():
    assert (
        _clean_title("Dongdaemun Design Plaza (동대문디자인플라자 (DDP))")
        == "Dongdaemun Design Plaza"
    )


def test_clean_title_keeps_english_parens():
    assert _clean_title("Museum (Main Hall)") == "Museum (Main Hall)"


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
