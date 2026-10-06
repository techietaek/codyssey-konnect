"""결과 상태 3종 산정 (A3, FR-C3 · PRD §5.4).

내부 판정 순서:
  1) Hard 충돌(영업외·휴무) → 추천 제외(None)
  2) (조정 가능한 조건 불일치 → 조건 완화 대안) ← 예산/Soft 조건 필요, A5 이후
  3) 명확한 불일치 없으나 핵심정보 미확인 → 추가 확인 필요(check_needed)
  4) 핵심조건 확인·충돌 없음 → 조건 충족(fits)

미확인을 긍정으로 바꾸지 않는다: 가격 unknown/partial 또는 시간 UNCERTAIN 이면 fits 아님.
"""

from __future__ import annotations

from app.domain.timing import TimingVerdict
from app.models.recommend import Candidate, PriceStatus, ResultStatus, UnconfirmedFlag


def resolve_status(
    candidate: Candidate, verdict: TimingVerdict
) -> tuple[ResultStatus | None, list[UnconfirmedFlag]]:
    """(상태, flags) 반환. 상태 None = Hard 제외(정상 추천에서 뺀다)."""
    if verdict is TimingVerdict.CLOSED:
        return None, []

    # 가격은 free/paid 만 '확인됨'으로 본다(partial·unknown 은 추가 확인).
    price_known = candidate.price.status in (PriceStatus.FREE, PriceStatus.PAID)

    flags: list[UnconfirmedFlag] = []
    if candidate.price.status is PriceStatus.UNKNOWN:
        flags.append(UnconfirmedFlag(text="Price needs checking"))
    elif candidate.price.status is PriceStatus.PARTIAL_OR_AMBIGUOUS:
        flags.append(UnconfirmedFlag(text="Price varies · check details"))
    if verdict is TimingVerdict.UNCERTAIN:
        flags.append(UnconfirmedFlag(text="Hours need checking"))

    if verdict is TimingVerdict.OPEN and price_known:
        return ResultStatus.FITS, []
    return ResultStatus.CHECK_NEEDED, flags
