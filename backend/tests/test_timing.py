"""운영시간·휴무 판정 테스트 (A3). 확실할 때만 CLOSED, 애매하면 UNCERTAIN."""

from __future__ import annotations

import calendar
from datetime import datetime

from app.domain.timing import (
    ExtractedHours,
    TimingVerdict,
    judge_extracted_hours,
    judge_timing,
    operating_hours_text,
    parse_closed_weekdays,
    parse_last_admission,
    parse_time_ranges,
    should_retry_hours_with_llm,
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


# ── 행사 기간(축제·공연) ──
def test_ended_event_excluded():
    # 2025-10-26 종료 공연을 2026-10-06에 방문 → CLOSED(종료)
    intro = {"eventstartdate": "20251010", "eventenddate": "20251026"}
    assert J(intro) is TimingVerdict.CLOSED


def test_future_event_excluded():
    intro = {"eventstartdate": "20271010", "eventenddate": "20271026"}
    assert J(intro) is TimingVerdict.CLOSED


def test_running_event_not_closed_by_dates():
    # 기간 내(2026-10-06 포함) → 날짜로는 CLOSED 아님(운영시간 판정으로)
    intro = {
        "eventstartdate": "20261001",
        "eventenddate": "20261031",
        "usetimefestival": "10:00-18:00",
    }
    assert J(intro) is TimingVerdict.OPEN


def test_window_to_midnight_still_open():
    # 종료가 다음날 00:00(시작일 24:00 경계) → 그날 끝으로 처리, 영업시간과 겹침
    end_midnight = datetime(2026, 10, 7, 0, 0)
    assert (
        judge_timing(
            {"usetime": "10:00-22:00"}, datetime(2026, 10, 6, 20, 0), end_midnight
        )[0]
        is TimingVerdict.OPEN
    )


# ── LLM 추출 hours 재판정 (3단계, 보수적: OPEN 승격만) ──
def test_retry_gate_only_for_parse_difficulty():
    # regex가 '텍스트 있음·파싱 애매'로 UNCERTAIN → 재시도 대상
    assert should_retry_hours_with_llm(
        TimingVerdict.UNCERTAIN, "operating hours not parseable"
    )
    assert should_retry_hours_with_llm(
        TimingVerdict.UNCERTAIN, "operating hours need checking"
    )
    # 빈값/숙박전용/이미 확정은 재시도 안 함
    assert not should_retry_hours_with_llm(
        TimingVerdict.UNCERTAIN, "operating hours not provided"
    )
    assert not should_retry_hours_with_llm(
        TimingVerdict.OPEN, "open during your time window"
    )


def test_operating_hours_text_picks_first():
    assert operating_hours_text({"usetimeculture": "09:00-18:00"}) == "09:00-18:00"
    assert operating_hours_text({}) == ""


def test_extracted_open_promotes():
    h = ExtractedHours(determinable=True, open_time="09:00", close_time="18:00")
    assert judge_extracted_hours(h, DAY, DAY_END)[0] is TimingVerdict.OPEN


def test_extracted_always_open():
    h = ExtractedHours(determinable=True, always_open=True)
    assert judge_extracted_hours(h, DAY, DAY_END)[0] is TimingVerdict.OPEN


def test_extracted_not_determinable_stays_uncertain():
    h = ExtractedHours(determinable=False)
    assert judge_extracted_hours(h, DAY, DAY_END)[0] is TimingVerdict.UNCERTAIN


def test_extracted_non_overlap_not_hard_closed():
    # 창(10~14)과 안 겹쳐도 LLM 단독 CLOSED 금지 → UNCERTAIN 유지
    h = ExtractedHours(determinable=True, open_time="18:00", close_time="21:00")
    assert judge_extracted_hours(h, DAY, DAY_END)[0] is TimingVerdict.UNCERTAIN


def test_extracted_after_last_admission_stays_uncertain():
    h = ExtractedHours(
        determinable=True, open_time="09:00", close_time="18:00", last_admission="09:30"
    )
    late = datetime(2026, 10, 6, 10, 0)
    assert judge_extracted_hours(h, late, DAY_END)[0] is TimingVerdict.UNCERTAIN
