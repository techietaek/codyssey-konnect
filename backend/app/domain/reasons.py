"""추천 이유(Reason) 선택 (A5, FR-C4 · PRD §5.2 R-09).

LLM이 이유를 '생성'하지 않는다 — 확인된 근거(유형·가격·영업·거리) + 사용자 조건 +
매치 규칙으로 Reason Copy Dictionary v1.0의 '고정 문구'를 코드가 고른다.
- 후보당 0~2개(Primary 1 + Secondary 1). 0개면 영역 생략(강제 채움 금지).
- 미확인 근거엔 Fit을 붙이지 않는다(가격 미확인 → budget reason 금지 등).
- 내부 Fit명은 노출하지 않는다(코드는 내부용, text만 사용자 노출).
"""

from __future__ import annotations

from app.domain.budget import BudgetVerdict
from app.domain.timing import TimingVerdict
from app.models.recommend import (
    Candidate,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    PriceStatus,
    Reason,
)

# Reason Copy Dictionary v1.0 (PRD 부록 B) — A 즉시추천에서 쓰는 부분집합
REASON_COPY = {
    "T03": "Open when you can visit",
    "M03": "Shortest trip among these options",
    "I01": "Matches your interest in traditional culture",
    "I02": "Matches your interest in palaces and historic sites",
    "I03": "Matches your interest in hands-on experiences",
    "I04": "Matches your interest in art and exhibitions",
    "I05": "Matches your interest in live performances",
    "I06": "Matches your interest in festivals and events",
    "B01": "Within your budget",
    "B02": "Matches your free-only request",
}

_INTEREST_CODE = {
    InterestCode.TRADITIONAL: "I01",
    InterestCode.PALACES_HISTORIC: "I02",
    InterestCode.HANDS_ON: "I03",
    InterestCode.ART_EXHIBITIONS: "I04",
    InterestCode.LIVE_PERFORMANCES: "I05",
    InterestCode.FESTIVALS_EVENTS: "I06",
}

# 후보 유형이 충족하는 관심사(내부 5유형↔6관심사, 1:1 아님)
_TYPE_INTERESTS = {
    ExperienceType.HISTORIC_VISIT: {
        InterestCode.PALACES_HISTORIC,
        InterestCode.TRADITIONAL,
    },
    ExperienceType.EXHIBITION: {InterestCode.ART_EXHIBITIONS},
    ExperienceType.PERFORMANCE: {InterestCode.LIVE_PERFORMANCES},
    ExperienceType.FESTIVAL_EVENT: {InterestCode.FESTIVALS_EVENTS},
    ExperienceType.HANDS_ON: {InterestCode.HANDS_ON, InterestCode.TRADITIONAL},
    ExperienceType.DEFAULT: set(),
}


def select_reasons(
    cand: Candidate,
    cond: ParsedConditions,
    timing: TimingVerdict,
    budget: BudgetVerdict,
    is_nearest: bool,
) -> list[Reason]:
    """(priority 낮을수록 우선) 중에서 최대 2개. 근거 있을 때만."""
    picks: list[tuple[int, str]] = []

    # 1) 관심사 — 확정 유형이 사용자가 말한 관심사와 매치
    satisfied = _TYPE_INTERESTS.get(cand.type, set())
    for ic in cond.interests:
        if ic in satisfied:
            picks.append((1, _INTEREST_CODE[ic]))
            break

    # 2) 예산 — 확정 가격이 조건을 '충족'할 때만 (OVER/UNKNOWN 이면 금지)
    if budget is BudgetVerdict.OK:
        if cond.free_only and cand.price.status is PriceStatus.FREE:
            picks.append((2, "B02"))
        elif cond.budget_krw is not None and cand.price.status in (
            PriceStatus.FREE,
            PriceStatus.PAID,
        ):
            picks.append((2, "B01"))

    # 3) 시간 — 영업이 확인될 때만
    if timing is TimingVerdict.OPEN:
        picks.append((3, "T03"))

    # 4) 이동 — 최근접 1개(후보가 복수일 때만 의미)
    if is_nearest:
        picks.append((4, "M03"))

    picks.sort(key=lambda x: x[0])
    out: list[Reason] = []
    seen: set[str] = set()
    for _prio, code in picks:
        if code in seen:
            continue
        seen.add(code)
        out.append(Reason(code=code, text=REASON_COPY[code]))
        if len(out) >= 2:
            break
    return out
