"""예산 판정 (A5, PRD §5.3·§6.2).

사용자가 명시한 예산/무료요청 vs 확인된 가격을 비교한다.
- 초과(OVER): 조정 가능한 조건 불일치 → 조건 완화 대안(alternative).
- 비교 불가(UNKNOWN): 가격 미확인 → 긍정으로 메우지 않음(무료 추정 금지).
확인된 일반 판매가 기준으로만 비교(학생·얼리버드 등 조건부 할인은 근거로 쓰지 않음).
"""

from __future__ import annotations

import re
from enum import Enum

from app.models.recommend import Candidate, ParsedConditions, PriceStatus


class BudgetVerdict(str, Enum):
    OK = "ok"  # 예산 내 또는 예산 제약 없음
    OVER = "over"  # 예산 초과 / 무료요청인데 유료
    UNKNOWN = "unknown"  # 가격 미확인 → 비교 불가


def _general_price(raw: str | None) -> int | None:
    """예산 비교용 '일반 판매가' 추출. 조건부 할인(학생·청소년·어린이)은 쓰지 않는다
    (PRD §6.2). 대표가가 모호하면 None(비교 불가 → UNKNOWN)."""
    if not raw:
        return None
    # 1) 'Adult(s) N won' 성인 일반가 우선
    m = re.search(r"adults?\D{0,15}?(\d[\d,]{2,})\s*(?:won|krw|₩)?", raw, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))
    # 2) 원화 금액이 하나뿐이면 그 값
    nums = re.findall(r"(\d[\d,]{2,})\s*(?:won|krw|₩)", raw, re.IGNORECASE)
    if not nums:
        nums = re.findall(r"₩\s*(\d[\d,]{2,})", raw)
    uniq = sorted({int(n.replace(",", "")) for n in nums})
    if len(uniq) == 1:
        return uniq[0]
    # 3) 금액 여러 개 + Adult 라벨 없음 → 대표가 모호 → 비교 불가
    return None


def judge_budget(cand: Candidate, cond: ParsedConditions) -> BudgetVerdict:
    free_only = cond.free_only
    budget = cond.budget_krw
    if not free_only and budget is None:
        return BudgetVerdict.OK  # 예산 제약 없음

    ps = cand.price.status
    if free_only:
        if ps is PriceStatus.FREE:
            return BudgetVerdict.OK
        if ps is PriceStatus.PAID:
            return BudgetVerdict.OVER
        return BudgetVerdict.UNKNOWN  # partial/unknown → 무료 확정 불가

    # budget_krw 설정됨
    if ps is PriceStatus.FREE:
        return BudgetVerdict.OK
    if ps is PriceStatus.PAID:
        m = _general_price(cand.price.raw)
        if m is None:
            return BudgetVerdict.UNKNOWN
        return BudgetVerdict.OK if m <= budget else BudgetVerdict.OVER
    return BudgetVerdict.UNKNOWN
