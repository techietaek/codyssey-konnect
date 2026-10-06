"""예산 판정 테스트 (A5, PRD §6.2). 조건부 할인은 예산근거로 쓰지 않는다."""

from __future__ import annotations

from app.domain.budget import BudgetVerdict, judge_budget
from app.models.recommend import (
    Candidate,
    ParsedConditions,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
)


def _cand(status: PriceStatus, raw: str | None = None) -> Candidate:
    return Candidate(
        id="c",
        title="X",
        status=ResultStatus.CHECK_NEEDED,
        price=PriceInfo(
            status=status, display="d", raw=raw, provenance=Provenance.CONFIRMED
        ),
    )


def _cond(**kw) -> ParsedConditions:
    return ParsedConditions(**kw)


def test_no_constraint_is_ok():
    assert (
        judge_budget(_cand(PriceStatus.PAID, "10,000 won"), _cond()) is BudgetVerdict.OK
    )


def test_free_only_free_ok():
    assert (
        judge_budget(_cand(PriceStatus.FREE), _cond(free_only=True)) is BudgetVerdict.OK
    )


def test_free_only_paid_over():
    assert (
        judge_budget(_cand(PriceStatus.PAID, "3,000 won"), _cond(free_only=True))
        is BudgetVerdict.OVER
    )


def test_free_only_unknown_is_unknown():
    assert (
        judge_budget(_cand(PriceStatus.UNKNOWN), _cond(free_only=True))
        is BudgetVerdict.UNKNOWN
    )


def test_budget_within_ok():
    assert (
        judge_budget(
            _cand(PriceStatus.PAID, "Adults 3,000 won"), _cond(budget_krw=5000)
        )
        is BudgetVerdict.OK
    )


def test_budget_over():
    assert (
        judge_budget(
            _cand(PriceStatus.PAID, "Adults 8,000 won"), _cond(budget_krw=5000)
        )
        is BudgetVerdict.OVER
    )


def test_budget_uses_adult_not_discount():
    # Adult 8,000 / Teenager 5,000 → 성인 8,000 기준 → 예산 5,000 초과
    raw = "Individual - Adult 8,000 won / Teenager 5,000 won"
    assert (
        judge_budget(_cand(PriceStatus.PAID, raw), _cond(budget_krw=5000))
        is BudgetVerdict.OVER
    )


def test_budget_free_is_within():
    assert (
        judge_budget(_cand(PriceStatus.FREE), _cond(budget_krw=5000))
        is BudgetVerdict.OK
    )


def test_budget_ambiguous_prices_unknown():
    # Adult 라벨 없이 금액 여러 개 → 대표가 모호 → 비교 불가
    raw = "3,000 won / 5,000 won / 10,000 won"
    assert (
        judge_budget(_cand(PriceStatus.PAID, raw), _cond(budget_krw=4000))
        is BudgetVerdict.UNKNOWN
    )
