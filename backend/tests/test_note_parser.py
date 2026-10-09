"""note_parser 결정론 규칙 테스트 (LLM 불필요 부분만).

'free or cheap'/'cheap' = ≤₩30,000 선호(무료만 아님). LLM 이 놓쳐도 코드가 교정.
"""

from __future__ import annotations

from app.agent.note_parser import CHEAP_KRW, _apply_cheap_rule
from app.models.recommend import ParsedConditions


def test_free_or_cheap_sets_budget_not_free_only():
    out = _apply_cheap_rule("Free or cheap", ParsedConditions(free_only=True))
    assert out.budget_krw == CHEAP_KRW == 30000
    assert out.free_only is False  # 무료만으로 좁히지 않는다


def test_cheap_variants():
    for note in ["cheap", "affordable spots", "budget-friendly", "inexpensive please"]:
        out = _apply_cheap_rule(note, ParsedConditions())
        assert out.budget_krw == 30000, note


def test_explicit_amount_not_overridden():
    out = _apply_cheap_rule("cheap, under 10000", ParsedConditions(budget_krw=10000))
    assert out.budget_krw == 10000  # 구체 금액 우선


def test_free_only_without_cheap_stays_free_only():
    out = _apply_cheap_rule("only free experiences", ParsedConditions(free_only=True))
    assert out.free_only is True
    assert out.budget_krw is None


def test_no_cheap_word_is_noop():
    out = _apply_cheap_rule("quiet art galleries", ParsedConditions())
    assert out.budget_krw is None
    assert out.free_only is False
