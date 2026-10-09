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
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TimingVerdict(str, Enum):
    OPEN = "open"  # 가용시간 안에 확실히 영업
    CLOSED = "closed"  # 휴무/영업시간 외 — Hard 충돌(제외)
    UNCERTAIN = "uncertain"  # 판단 불가 — 추가 확인 필요


class EventPeriod(str, Enum):
    """날짜형 콘텐츠(축제·공연·행사)의 개최 기간 상태 — '끝난 것 금지' 판정용."""

    ACTIVE = "active"  # 방문일이 개최 기간 내 → 유지
    ENDED = "ended"  # 종료일 지남 → Hard 제외(이미 끝난 콘텐츠 금지)
    UPCOMING = "upcoming"  # 방문일 이전 시작 → 그 날엔 아직 없음, Hard 제외
    UNKNOWN = "unknown"  # 날짜 미상 → 기간 근거로 제외하지 않음(추정 금지)


def _parse_yyyymmdd(s: Any) -> date | None:
    t = str(s or "").strip()
    if len(t) != 8 or not t.isdigit():
        return None
    try:
        return date(int(t[:4]), int(t[4:6]), int(t[6:8]))
    except ValueError:
        return None


def judge_event_period(intro: dict[str, Any], ref_date: date) -> EventPeriod:
    """TourAPI eventstartdate/eventenddate 로 개최 기간 판정(방문일 기준).

    종료일이 방문일 이전이면 ENDED(이미 끝남), 시작일이 방문일 이후면 UPCOMING(아직 안 함).
    날짜가 하나도 없으면 UNKNOWN(기간으로 제외하지 않음 — 미확인을 '끝남'으로 단정 금지).
    """
    start = _parse_yyyymmdd(intro.get("eventstartdate"))
    end = _parse_yyyymmdd(intro.get("eventenddate"))
    if end and end < ref_date:
        return EventPeriod.ENDED
    if start and start > ref_date:
        return EventPeriod.UPCOMING
    if start or end:
        return EventPeriod.ACTIVE
    return EventPeriod.UNKNOWN


class ExtractedHours(BaseModel):
    """LLM이 공식 운영시간 자유텍스트에서 '추출'한 구조값 (생성 아님, A5 3단계).

    LLM은 쓰여있는 것만 추출한다. 확정 불가면 determinable=false → UNCERTAIN 유지.
    판정은 judge_extracted_hours(코드)가 하며, LLM 단독으로 Hard 제외(CLOSED)는 하지
    않는다(보수적 — 오추출로 유효 후보를 지우지 않게). UNCERTAIN→OPEN 승격만 허용.
    """

    determinable: bool = Field(
        description="True only if operating hours for the visit date are clearly stated in the text."
    )
    always_open: bool = Field(default=False, description="Open 24 hours / all day.")
    open_time: str | None = Field(
        default=None,
        description="Opening time 'HH:MM' (24h) for the visit date, else null.",
    )
    close_time: str | None = Field(
        default=None,
        description="Closing time 'HH:MM' (24h) for the visit date, else null.",
    )
    last_admission: str | None = Field(
        default=None, description="Last admission 'HH:MM' (24h) if stated, else null."
    )


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


def _parse_yyyymmdd(s: str | None) -> date | None:
    s = (s or "").strip()
    if len(s) == 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    return None


def judge_event_dates(
    intro: dict[str, Any], visit_date: date
) -> tuple[TimingVerdict, str] | None:
    """축제·공연(type 85)의 행사 기간 판정. 방문일이 기간 밖이면 CLOSED(Hard).

    기간 정보가 없으면 None(행사 날짜로는 판단 안 함 → 운영시간 판정으로 진행).
    """
    start = _parse_yyyymmdd(intro.get("eventstartdate"))
    end = _parse_yyyymmdd(intro.get("eventenddate"))
    if end and visit_date > end:
        return TimingVerdict.CLOSED, "event has ended"
    if start and visit_date < start:
        return TimingVerdict.CLOSED, "event has not started yet"
    return None


def _window_end_time(start_dt: datetime, end_dt: datetime) -> time:
    # 종료가 다음날 자정(00:00)이면 '그날 끝(23:59)'으로 본다(FR-A2 경계).
    if end_dt.time() == time(0, 0) and end_dt.date() != start_dt.date():
        return time(23, 59)
    return end_dt.time()


def judge_timing(
    intro: dict[str, Any], start_dt: datetime, end_dt: datetime
) -> tuple[TimingVerdict, str]:
    """행사기간·운영시간·휴무 → (판정, 사유). 사유는 trace/설명용."""
    # 0) 행사 기간 (축제·공연): 방문일이 기간 밖이면 Hard(종료/미개막)
    event = judge_event_dates(intro, start_dt.date())
    if event is not None:
        return event

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


# regex 로 UNCERTAIN(파싱불가/caveat) 이 된 자유텍스트만 LLM 파서로 재시도하기 위한 표식.
_LLM_RETRY_REASONS = ("operating hours not parseable", "operating hours need checking")


def operating_hours_text(intro: dict[str, Any]) -> str:
    """운영시간 자유텍스트(타입별 필드 중 첫 값). 없으면 ''. (LLM 파서 입력용)"""
    return _first(intro, _HOURS_KEYS)


def should_retry_hours_with_llm(verdict: TimingVerdict, reason: str) -> bool:
    """regex 가 '텍스트는 있으나 파싱 애매'로 UNCERTAIN 판정한 경우에만 LLM 재시도.
    빈값('not provided')·숙박전용은 LLM으로도 못 얻으므로 제외."""
    return verdict is TimingVerdict.UNCERTAIN and reason in _LLM_RETRY_REASONS


def _hhmm(s: str | None) -> time | None:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s or "")
    return _to_time(int(m.group(1)), int(m.group(2))) if m else None


_MIN_WINDOW = timedelta(minutes=30)


def effective_end_at(
    start_at: datetime,
    form_end_at: datetime,
    end_time: str | None,
    duration_minutes: int | None,
) -> tuple[datetime, str | None]:
    """note 가 명시한 종료시각/소요시간으로 가용창을 '더 좁게'만 조정(보수적 narrow, §11).

    가용시간을 과대평가하지 않도록 명시값과 폼 종료 중 **더 이른 쪽(min)** 을 택한다
    (없는 시간을 벌어 장소를 OPEN 으로 오판하지 않게). 창을 넓히지는 않는다 — Request 우선
    이되 '덜 가진' 쪽으로만 간다. note 값이 무효이거나 결과가 30분 미만/역전이면 폼 값을
    유지(무시 — 사용자가 말하지 않은 시간을 지어내지 않고 추천도 막지 않는다. raise 하지 않음:
    루프의 generic 핸들러가 모호한 오류로 삼키지 않게). 반환: (effective_end, applied|None).
    applied 는 실제 적용된 근거('end_time'|'duration'), 미적용 시 None(trace 용).
    """
    candidates: list[tuple[datetime, str]] = []
    t = _hhmm(end_time)
    if t is not None:
        candidates.append(
            (datetime.combine(start_at.date(), t, tzinfo=start_at.tzinfo), "end_time")
        )
    if duration_minutes is not None and duration_minutes > 0:
        candidates.append((start_at + timedelta(minutes=duration_minutes), "duration"))
    if not candidates:
        return form_end_at, None
    end, source = min(candidates, key=lambda c: c[0])
    if end >= form_end_at:  # 폼보다 넓히지 않음(보수적)
        return form_end_at, None
    if end - start_at < _MIN_WINDOW:  # 30분 미만/역전 → 무시(지어내지 않음, raise 안 함)
        return form_end_at, None
    return end, source


def judge_extracted_hours(
    h: ExtractedHours, start_dt: datetime, end_dt: datetime
) -> tuple[TimingVerdict, str]:
    """LLM 추출값으로 재판정. **OPEN 승격만** — 확정 못하면 UNCERTAIN(기존 유지).
    LLM 단독 Hard 제외(CLOSED)는 하지 않는다(보수적, 오추출 방어)."""
    if not h.determinable:
        return TimingVerdict.UNCERTAIN, "hours not determinable from text"
    if h.always_open:
        return TimingVerdict.OPEN, "open 24 hours (parsed)"
    s = _hhmm(h.open_time)
    e = _hhmm(h.close_time)
    if not (s and e and e > s):
        return TimingVerdict.UNCERTAIN, "hours not determinable from text"
    ws = start_dt.time()
    we = _window_end_time(start_dt, end_dt)
    if not (s < we and e > ws):  # 안 겹쳐도 LLM 단독 CLOSED 안 함 → UNCERTAIN 유지
        return TimingVerdict.UNCERTAIN, "parsed hours do not overlap"
    last = _hhmm(h.last_admission)
    if last is not None and ws > last:
        return TimingVerdict.UNCERTAIN, "after last admission (parsed)"
    return TimingVerdict.OPEN, "open during your time window (parsed)"
