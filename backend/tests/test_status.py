"""3상태 산정 테스트 (A3, FR-C3·§5.4)."""

from __future__ import annotations

from app.domain.status import resolve_status
from app.domain.timing import TimingVerdict
from app.models.recommend import (
    Candidate,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
)


def _cand(price_status: PriceStatus) -> Candidate:
    return Candidate(
        id="c1",
        title="X",
        status=ResultStatus.CHECK_NEEDED,
        price=PriceInfo(
            status=price_status,
            display="d",
            provenance=(
                Provenance.CONFIRMED
                if price_status in (PriceStatus.FREE, PriceStatus.PAID)
                else Provenance.UNCONFIRMED
            ),
        ),
    )


def test_closed_is_excluded():
    status, _flags = resolve_status(_cand(PriceStatus.FREE), TimingVerdict.CLOSED)
    assert status is None  # 정상 추천에서 제외


def test_open_and_price_known_is_fits():
    status, flags = resolve_status(_cand(PriceStatus.FREE), TimingVerdict.OPEN)
    assert status is ResultStatus.FITS
    assert flags == []


def test_open_but_price_unknown_is_check():
    status, flags = resolve_status(_cand(PriceStatus.UNKNOWN), TimingVerdict.OPEN)
    assert status is ResultStatus.CHECK_NEEDED
    assert "Price needs checking" in [f.text for f in flags]


def test_uncertain_hours_is_check_with_flag():
    status, flags = resolve_status(_cand(PriceStatus.PAID), TimingVerdict.UNCERTAIN)
    assert status is ResultStatus.CHECK_NEEDED
    assert "Hours need checking" in [f.text for f in flags]


def test_uncertain_hours_and_unknown_price_has_both_flags():
    _status, flags = resolve_status(_cand(PriceStatus.UNKNOWN), TimingVerdict.UNCERTAIN)
    texts = [f.text for f in flags]
    assert "Price needs checking" in texts and "Hours need checking" in texts


def test_partial_price_is_not_fits():
    status, flags = resolve_status(
        _cand(PriceStatus.PARTIAL_OR_AMBIGUOUS), TimingVerdict.OPEN
    )
    assert status is ResultStatus.CHECK_NEEDED
    assert "Price varies · check details" in [f.text for f in flags]
