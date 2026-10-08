"""서울문화포털(culturalEventInfo) 정규화 단위 테스트.

신뢰 게이트(CLAUDE §6):
- 요금 빈값은 free 가 아니라 unknown. IS_FREE='무료'만 확인된 Free.
- 운영시간은 미제공 → 미확인(시간 지어내지 않음).
- 좌표는 LOT/LAT 이름이 뒤바뀐 소스라도 범위로 올바른 (lat,lng) 복원, 범위 밖/누락은 drop.
- 기간(STRTDATE/END_DATE)은 결정론 판정(judge_event_period)으로 끝난 행사 Hard 제외.
"""

from __future__ import annotations

from datetime import date

from app.domain.normalize import (
    _seoul_type,
    _valid_seoul_coords,
    normalize_seoul_event,
    seoul_event_intro,
)
from app.domain.timing import EventPeriod, judge_event_period
from app.models.recommend import ExperienceType, PriceStatus


def _row(**over):
    base = {
        "TITLE": "서울빛초롱축제",
        "CODENAME": "축제",
        "USE_FEE": "",
        "IS_FREE": "무료",
        "STRTDATE": "2026-10-01 00:00:00.0",
        "END_DATE": "2026-10-31 00:00:00.0",
        "LOT": "37.5665",  # 위도 범위 값 (이름은 LOT 이지만 실제 위도)
        "LAT": "126.9780",  # 경도 범위 값
        "ORG_LINK": "https://example.seoul.go.kr/event",
        "MAIN_IMG": "https://example.seoul.go.kr/img.jpg",
        "PROGRAM": "<p>전통 등 전시</p>",
    }
    base.update(over)
    return base


# ── 좌표: 이름 뒤바뀜 안전 복원 ──
def test_coords_swapped_names_resolved_by_range():
    lat, lng = _valid_seoul_coords(_row())
    assert 37.0 < lat < 38.0  # 위도
    assert 126.0 < lng < 128.0  # 경도


def test_coords_even_if_physically_swapped_values():
    # 값이 물리적으로 바뀌어 들어와도 범위로 올바르게 배정
    lat, lng = _valid_seoul_coords(_row(LOT="126.9780", LAT="37.5665"))
    assert 37.0 < lat < 38.0
    assert 126.0 < lng < 128.0


def test_coords_missing_is_none():
    assert _valid_seoul_coords(_row(LOT="", LAT="")) is None


def test_coords_out_of_korea_is_none():
    assert _valid_seoul_coords(_row(LOT="0", LAT="0")) is None


# ── 요금: 무료 추정 금지 ──
def test_is_free_explicit_maps_free():
    cand = normalize_seoul_event(_row(USE_FEE="", IS_FREE="무료"))
    assert cand is not None
    assert cand.price.status is PriceStatus.FREE


def test_empty_fee_and_blank_isfree_is_unknown():
    cand = normalize_seoul_event(_row(USE_FEE="", IS_FREE=""))
    assert cand.price.status is PriceStatus.UNKNOWN


def test_paid_only_signal_is_unknown_amount():
    cand = normalize_seoul_event(_row(USE_FEE="", IS_FREE="유료"))
    assert cand.price.status is PriceStatus.UNKNOWN


def test_fee_with_amount_is_paid():
    cand = normalize_seoul_event(_row(USE_FEE="성인 5,000원", IS_FREE="유료"))
    assert cand.price.status is PriceStatus.PAID


# ── 정규화 산출물 ──
def test_source_badge_and_hours_unconfirmed():
    cand = normalize_seoul_event(_row())
    assert cand.source == "seoul"
    assert cand.time is None  # 시간 미제공 — 지어내지 않음
    assert any("Hours" in f.text for f in cand.flags)
    assert cand.id.startswith("seoul-")


def test_korean_title_kept_as_is():
    # E1 — 영문화는 롤아웃 4단계. 지금은 국문 제목 그대로.
    cand = normalize_seoul_event(_row(TITLE="남산골한옥마을 공연"))
    assert cand.title == "남산골한옥마을 공연"


def test_no_title_is_dropped():
    assert normalize_seoul_event(_row(TITLE="")) is None


def test_non_http_link_dropped():
    cand = normalize_seoul_event(_row(ORG_LINK="n/a", MAIN_IMG=""))
    assert cand.official_links == []
    assert cand.image_url is None


# ── 유형 매핑 ──
def test_type_mapping():
    assert _seoul_type("전시/미술") is ExperienceType.EXHIBITION
    assert _seoul_type("콘서트") is ExperienceType.PERFORMANCE
    assert _seoul_type("축제") is ExperienceType.FESTIVAL_EVENT
    assert _seoul_type("교육/체험") is ExperienceType.HANDS_ON
    assert _seoul_type("기타") is ExperienceType.FESTIVAL_EVENT  # 기본


# ── 기간 판정(결정론 재사용) ──
def test_event_intro_maps_period_fields():
    intro = seoul_event_intro(_row())
    assert intro["eventstartdate"] == "20261001"
    assert intro["eventenddate"] == "20261031"


def test_ended_event_is_hard_excluded_period():
    intro = seoul_event_intro(_row(END_DATE="2026-01-05"))
    assert judge_event_period(intro, date(2026, 10, 8)) is EventPeriod.ENDED


def test_upcoming_event_period():
    intro = seoul_event_intro(_row(STRTDATE="2026-12-01", END_DATE="2026-12-31"))
    assert judge_event_period(intro, date(2026, 10, 8)) is EventPeriod.UPCOMING


def test_active_event_period():
    intro = seoul_event_intro(_row())
    assert judge_event_period(intro, date(2026, 10, 8)) is EventPeriod.ACTIVE


def test_missing_dates_unknown_not_excluded():
    intro = seoul_event_intro(_row(STRTDATE="", END_DATE=""))
    assert judge_event_period(intro, date(2026, 10, 8)) is EventPeriod.UNKNOWN
