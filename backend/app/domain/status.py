"""결과 상태 3종 산정 (A3+A5, FR-C3 · PRD §5.4).

내부 판정 순서:
  1) Hard 충돌(영업외·휴무·행사종료) → 추천 제외(None)
  2) 조정 가능한 조건 불일치(예산 초과) → 조건 완화 대안(alternative)
  3) 명확한 불일치 없으나 핵심정보 미확인 → 추가 확인 필요(check_needed)
  4) 핵심조건 확인·충돌 없음 → 조건 충족(fits)

미확인을 긍정으로 바꾸지 않는다. alternative 는 차이를 flag로 명시하고
해당 조건에 충족 Reason을 붙이지 않는다(reasons 단계에서 budget OK 아닐 때 제외).
"""

from __future__ import annotations

from app.domain.budget import BudgetVerdict
from app.domain.timing import TimingVerdict
from app.models.recommend import (
    Candidate,
    ParsedConditions,
    PriceStatus,
    ResultStatus,
    UnconfirmedFlag,
)


def resolve_status(
    candidate: Candidate,
    timing: TimingVerdict,
    budget: BudgetVerdict,
    cond: ParsedConditions,
) -> tuple[ResultStatus | None, list[UnconfirmedFlag]]:
    """(상태, flags). None = Hard 제외."""
    if timing is TimingVerdict.CLOSED:
        return None, []

    # 2) 예산 초과 → 조건 완화 대안 (차이 명시)
    if budget is BudgetVerdict.OVER:
        flags: list[UnconfirmedFlag] = []
        if cond.free_only and cond.budget_krw is None:
            flags.append(UnconfirmedFlag(text="Not a free option"))
        else:
            flags.append(UnconfirmedFlag(text="Above your budget"))
        if timing is TimingVerdict.UNCERTAIN:
            flags.append(UnconfirmedFlag(text="Hours need checking"))
        return ResultStatus.ALTERNATIVE, flags

    # 3~4) 미확인 분리 후 fits/check
    price_known = candidate.price.status in (PriceStatus.FREE, PriceStatus.PAID)
    flags = []
    if candidate.price.status is PriceStatus.UNKNOWN:
        flags.append(UnconfirmedFlag(text="Price needs checking"))
    elif candidate.price.status is PriceStatus.PARTIAL_OR_AMBIGUOUS:
        flags.append(UnconfirmedFlag(text="Price varies · check details"))
    if timing is TimingVerdict.UNCERTAIN:
        flags.append(UnconfirmedFlag(text="Hours need checking"))

    budget_ok = budget in (BudgetVerdict.OK,)  # UNKNOWN 예산은 fits 아님
    if timing is TimingVerdict.OPEN and price_known and budget_ok:
        return ResultStatus.FITS, []
    return ResultStatus.CHECK_NEEDED, flags
