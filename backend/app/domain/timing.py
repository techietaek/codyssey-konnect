"""운영시간·휴무 판정 (A3, PRD §5.3·§6.2).

TourAPI 상세(detailIntro2)의 자유기술 운영시간/휴무를 파싱해 사용자의 가용시간
[start_at, end_at] 안에 '실제로 방문 가능한가'를 판정한다.

신뢰 원칙:
- 확실할 때만 CLOSED(Hard 제외). 계절·복수시설·'문의' 등 애매하면 CLOSED 로 단정하지
  않고 UNCERTAIN(추가 확인 필요)으로 둔다. 미확인을 영업중으로도 추정하지 않는다.
- 숫자 운영시간은 결정론적 코드로만 비교(LLM 미사용).
"""

from __future__ import annotations

import re
from datetime import datetime, time
from enum import Enum
from typing import Any


class TimingVerdict(str, Enum):
    OPEN = "open"  # 가용시간 안에 확실히 영업
    CLOSED = "closed"  # 휴무/영업시간 외 — Hard 충돌(제외)
    UNCERTAIN = "uncertain"  # 판단 불가 — 추가 확인 필요


_HOURS_KEYS = [
    "usetime",
    "usetimeculture",
    "usetimefestival",
    "opentime",
    "usetimeleports",
]
_REST_KEYS = ["restdate", "restdateculture", "restdatefestival", "restdateleports"]

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-~–—]\s*(\d{1,2}):(\d{2})")
_LAST_ADM_RE = re.compile(
    r"(?:last admission|last entry|last ticket|입장마감)\D*?(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)
_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.IGNORECASE
)
_CAVEAT_WORDS = (
    "inquire",
    "by appointment",
    "reservation",
    "vary",
    "varies",
    "seasonal",
    "문의",
    "상이",
    "계절",
)
_LODGING = ("check-in", "check in", "check-out", "checkout")
_ALWAYS_OPEN = ("open all year", "no closed", "everyday", "연중무휴", "없음")
_ALL_DAY = ("24 hr", "24 hour", "24-hour", "24 hours", "open 24", "24시간", "24시")


def _first(d: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _to_time(h: int, m: int) -> time | None:
    if h == 24 and m == 0:
        return time(23, 59)  # 24:00 = 하루 끝
    if 0 <= h <= 23 and 0 <= m <= 59:
        return time(h, m)
    return None


def parse_time_ranges(text: str) -> list[tuple[time, time]]:
    out: list[tuple[time, time]] = []
    for h1, m1, h2, m2 in _RANGE_RE.findall(text):
        s = _to_time(int(h1), int(m1))
        e = _to_time(int(h2), int(m2))
        if s and e and e > s:  # 자정 넘김(overnight)은 제외(문화시설엔 희귀)
            out.append((s, e))
    return out


def parse_last_admission(text: str) -> time | None:
    m = _LAST_ADM_RE.search(text)
    if m:
        return _to_time(int(m.group(1)), int(m.group(2)))
    return None


def parse_closed_weekdays(restdate: str) -> set[int]:
    """휴무 요일 집합(0=월~6=일). 파싱 불가(공휴일 등)는 빈 집합."""
    low = restdate.lower()
    if any(w in low for w in _ALWAYS_OPEN):
        return set()
    closed: set[int] = set()
    if "weekend" in low:
        closed |= {5, 6}
    if "weekday" in low and "weekdays" in low:  # 'closed on weekdays' (드묾)
        closed |= {0, 1, 2, 3, 4}
    for name, idx in _WEEKDAYS.items():
        if name in low:
            closed.add(idx)
    return closed


def _has_caveat(text: str, n_ranges: int) -> bool:
    low = text.lower()
    return (
        n_ranges > 1
        or any(w in low for w in _CAVEAT_WORDS)
        or bool(_MONTH_RE.search(low))
    )


def _window_end_time(start_dt: datetime, end_dt: datetime) -> time:
    # 종료가 다음날 자정(00:00)이면 '그날 끝(23:59)'으로 본다(FR-A2 경계).
    if end_dt.time() == time(0, 0) and end_dt.date() != start_dt.date():
        return time(23, 59)
    return end_dt.time()


def judge_timing(
    intro: dict[str, Any], start_dt: datetime, end_dt: datetime
) -> tuple[TimingVerdict, str]:
    """운영시간·휴무 → (판정, 사유). 사유는 trace/설명용."""
    # 1) 요일 휴무 (확인되면 Hard)
    closed = parse_closed_weekdays(_first(intro, _REST_KEYS))
    if start_dt.weekday() in closed:
        return TimingVerdict.CLOSED, "closed on this day of the week"

    # 2) 운영시간
    hours = _first(intro, _HOURS_KEYS)
    if not hours:
        return TimingVerdict.UNCERTAIN, "operating hours not provided"
    low = hours.lower()
    if any(k in low for k in _LODGING):
        return TimingVerdict.UNCERTAIN, "only lodging hours available"
    if any(k in low for k in _ALL_DAY):
        return TimingVerdict.OPEN, "open 24 hours"
    ranges = parse_time_ranges(hours)
    if not ranges:
        return TimingVerdict.UNCERTAIN, "operating hours not parseable"

    caveat = _has_caveat(hours, len(ranges))
    ws = start_dt.time()
    we = _window_end_time(start_dt, end_dt)
    overlap = any(s < we and e > ws for s, e in ranges)
    last = parse_last_admission(hours)
    too_late = last is not None and ws > last

    if not caveat:
        if not overlap:
            return TimingVerdict.CLOSED, "closed during your time window"
        if too_late:
            return TimingVerdict.CLOSED, "after last admission"
        return TimingVerdict.OPEN, "open during your time window"
    # 계절·복수시설·문의 등 → 단정하지 않음
    return TimingVerdict.UNCERTAIN, "operating hours need checking"
