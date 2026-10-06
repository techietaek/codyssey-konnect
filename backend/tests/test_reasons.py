"""Reason 선택 테스트 (A5, FR-C4). 확정 근거만, 최대 2개, 미확인엔 Fit 금지."""

from __future__ import annotations

from app.domain.budget import BudgetVerdict
from app.domain.reasons import select_reasons
from app.domain.timing import TimingVerdict
from app.models.recommend import (
    Candidate,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
)


def _cand(etype=ExperienceType.EXHIBITION, price=PriceStatus.FREE) -> Candidate:
    return Candidate(
        id="c",
        title="X",
        type=etype,
        status=ResultStatus.CHECK_NEEDED,
        price=PriceInfo(status=price, display="d", provenance=Provenance.CONFIRMED),
    )


def _codes(reasons):
    return [r.code for r in reasons]


def test_interest_match():
    r = select_reasons(
        _cand(ExperienceType.EXHIBITION),
        ParsedConditions(interests=[InterestCode.ART_EXHIBITIONS]),
        TimingVerdict.UNCERTAIN,
        BudgetVerdict.UNKNOWN,
        is_nearest=False,
    )
    assert "I04" in _codes(r)


def test_no_interest_reason_when_type_mismatch():
    r = select_reasons(
        _cand(ExperienceType.HISTORIC_VISIT),
        ParsedConditions(interests=[InterestCode.ART_EXHIBITIONS]),
        TimingVerdict.UNCERTAIN,
        BudgetVerdict.UNKNOWN,
        is_nearest=False,
    )
    assert "I04" not in _codes(r)


def test_free_only_reason_when_ok():
    r = select_reasons(
        _cand(price=PriceStatus.FREE),
        ParsedConditions(free_only=True),
        TimingVerdict.OPEN,
        BudgetVerdict.OK,
        is_nearest=False,
    )
    assert "B02" in _codes(r)


def test_no_budget_reason_when_over():
    # 예산 초과(alternative)엔 충족 reason 금지
    r = select_reasons(
        _cand(price=PriceStatus.PAID),
        ParsedConditions(budget_krw=5000),
        TimingVerdict.OPEN,
        BudgetVerdict.OVER,
        is_nearest=False,
    )
    assert "B01" not in _codes(r) and "B02" not in _codes(r)


def test_time_reason_only_when_open():
    r_open = select_reasons(
        _cand(), ParsedConditions(), TimingVerdict.OPEN, BudgetVerdict.OK, False
    )
    r_unc = select_reasons(
        _cand(), ParsedConditions(), TimingVerdict.UNCERTAIN, BudgetVerdict.OK, False
    )
    assert "T03" in _codes(r_open)
    assert "T03" not in _codes(r_unc)


def test_nearest_gets_movement():
    r = select_reasons(
        _cand(),
        ParsedConditions(),
        TimingVerdict.UNCERTAIN,
        BudgetVerdict.UNKNOWN,
        is_nearest=True,
    )
    assert "M03" in _codes(r)


def test_max_two_reasons():
    r = select_reasons(
        _cand(ExperienceType.EXHIBITION, PriceStatus.FREE),
        ParsedConditions(interests=[InterestCode.ART_EXHIBITIONS], free_only=True),
        TimingVerdict.OPEN,
        BudgetVerdict.OK,
        is_nearest=True,
    )
    assert len(r) <= 2
    # 우선순위: 관심사(1) + 예산(2) 먼저
    assert _codes(r) == ["I04", "B02"]


def test_zero_reasons_possible():
    r = select_reasons(
        _cand(ExperienceType.DEFAULT, PriceStatus.UNKNOWN),
        ParsedConditions(),
        TimingVerdict.UNCERTAIN,
        BudgetVerdict.UNKNOWN,
        is_nearest=False,
    )
    assert r == []  # 강제 채움 금지
