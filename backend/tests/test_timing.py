"""운영시간·휴무 판정 테스트 (A3). 확실할 때만 CLOSED, 애매하면 UNCERTAIN."""

from __future__ import annotations

import calendar
from datetime import datetime

from app.domain.timing import (
    TimingVerdict,
    judge_timing,
    parse_closed_weekdays,
    parse_last_admission,
    parse_time_ranges,
)

# 2026-10-06 는 화요일. 윈도우 10:00~14:00.
DAY = datetime(2026, 10, 6, 10, 0)
DAY_END = datetime(2026, 10, 6, 14, 0)
DAY_NAME = calendar.day_name[DAY.weekday()]  # 'Tuesday'


def J(intro, start=DAY, end=DAY_END):
    return judge_timing(intro, start, end)[0]


# ── 파싱 ──
def test_parse_single_range():
    assert parse_time_ranges("10:00-18:00") == [
        (__import__("datetime").time(10, 0), __import__("datetime").time(18, 0))
    ]


def test_parse_multiple_ranges():
    assert len(parse_time_ranges("Museum 10:00-18:00 / Tea house 10:00-22:50")) == 2


def test_parse_last_admission():
    from datetime import time

    assert parse_last_admission("10:00-18:00 (Last admission 17:30)") == time(17, 30)


def test_closed_weekdays():
    assert parse_closed_weekdays("Every Monday") == {0}
    assert parse_closed_weekdays("Weekends") == {5, 6}
    assert parse_closed_weekdays("Open all year round") == set()


# ── 판정 ──
def test_open_when_within_hours():
    assert J({"usetime": "09:00-18:00"}) is TimingVerdict.OPEN


def test_closed_outside_hours():
    # 19:00-22:00 영업 → 10~14 윈도우와 겹치지 않음 → Hard
    assert J({"usetime": "19:00-22:00"}) is TimingVerdict.CLOSED


def test_closed_on_rest_weekday():
    assert J({"usetime": "09:00-18:00", "restdate": DAY_NAME}) is TimingVerdict.CLOSED


def test_closed_after_last_admission():
    late_start = datetime(2026, 10, 6, 17, 45)
    late_end = datetime(2026, 10, 6, 19, 0)
    v = judge_timing(
        {"usetime": "10:00-18:00 (Last admission 17:30)"}, late_start, late_end
    )[0]
    assert v is TimingVerdict.CLOSED


def test_uncertain_no_hours():
    assert J({}) is TimingVerdict.UNCERTAIN


def test_uncertain_seasonal_multi_range():
    # 계절·복수 범위 → 단정하지 않음(겹쳐도 UNCERTAIN)
    hours = "March-October 09:00-18:00 / November-February 09:00-17:00"
    assert J({"usetime": hours}) is TimingVerdict.UNCERTAIN


def test_uncertain_lodging_hours():
    assert J({"usetime": "Check-in 15:00 / Check-out 11:00"}) is TimingVerdict.UNCERTAIN


def test_uncertain_inquire_caveat():
    assert J({"usetime": "10:00-20:00 (Inquire by phone)"}) is TimingVerdict.UNCERTAIN


def test_open_24_hours():
    assert J({"usetime": "Open 24 hr"}) is TimingVerdict.OPEN


def test_window_to_midnight_still_open():
    # 종료가 다음날 00:00(시작일 24:00 경계) → 그날 끝으로 처리, 영업시간과 겹침
    end_midnight = datetime(2026, 10, 7, 0, 0)
    assert (
        judge_timing(
            {"usetime": "10:00-22:00"}, datetime(2026, 10, 6, 20, 0), end_midnight
        )[0]
        is TimingVerdict.OPEN
    )
