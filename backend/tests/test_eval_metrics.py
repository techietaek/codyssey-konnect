"""eval/metrics 순수 집계 유닛테스트 (네트워크·LLM 무관 — CI 안전).

라이브 러너는 키·네트워크가 필요해 CI 에서 돌리지 않는다. 대신 지표 계산 로직
(recall@k·constraint 위반·empty·hard_exclude·percentile)을 결정론 QueryOutcome 으로 검증한다.
"""

from __future__ import annotations

from app.eval.metrics import (
    QueryOutcome,
    _percentile,
    aggregate,
    evaluate,
)


def _outcome(**kw) -> QueryOutcome:
    base = {
        "query_id": "q",
        "mode": "recommend",
        "titles": [],
        "statuses": [],
        "latency_ms": 100.0,
    }
    base.update(kw)
    return QueryOutcome(**base)


def test_recall_hit_case_insensitive_substring():
    o = _outcome(
        titles=["Gyeongbokgung Palace", "Jogyesa Temple"], statuses=["fits", "fits"]
    )
    v = evaluate(o, {"expect_title_any": ["PALACE"]})
    assert v.recall_applicable and v.recall_hit


def test_recall_miss_when_expected_absent():
    o = _outcome(titles=["Jogyesa Temple"], statuses=["fits"])
    v = evaluate(o, {"expect_title_any": ["palace", "hanok"]})
    assert v.recall_applicable and not v.recall_hit


def test_recall_not_applicable_without_expectation():
    o = _outcome(titles=["X"], statuses=["fits"])
    v = evaluate(o, {})
    assert not v.recall_applicable and not v.recall_hit


def test_forbidden_title_is_violation():
    o = _outcome(
        titles=["Gyeongbokgung Palace", "N Seoul Tower"], statuses=["fits", "fits"]
    )
    v = evaluate(o, {"forbid_title_any": ["gyeongbokgung"]})
    assert v.violations and not v.clean


def test_forbid_empty_violation_only_when_empty():
    empty = evaluate(_outcome(titles=[]), {"forbid_empty": True})
    assert any("0 results" in m for m in empty.violations)
    nonempty = evaluate(
        _outcome(titles=["A"], statuses=["fits"]), {"forbid_empty": True}
    )
    assert nonempty.clean


def test_structural_invariant_errors_flow_through():
    o = _outcome(
        titles=["A"],
        statuses=["fits"],
        extra_invariant_errors=["candidates=5 exceeds max 4"],
    )
    v = evaluate(o, {})
    assert "candidates=5 exceeds max 4" in v.violations and not v.clean


def test_fits_ratio_and_hard_exclude_rate():
    o = _outcome(
        titles=["A", "B", "C", "D"],
        statuses=["fits", "fits", "alternative", "check_needed"],
        considered=8,
        excluded_hard=2,
    )
    v = evaluate(o, {})
    assert v.fits_ratio == 0.5
    assert v.hard_exclude_rate == 0.25


def test_hard_exclude_rate_none_when_considered_but_no_excluded():
    # 루트 모드: considered 는 있어도 excluded_hard=None → rate 생략(크래시 금지).
    o = _outcome(
        titles=["A", "B"],
        statuses=["fits", "fits"],
        considered=12,
        excluded_hard=None,
    )
    v = evaluate(o, {})
    assert v.hard_exclude_rate is None


def test_error_outcome_excluded_from_recall_and_marks_error():
    o = _outcome(error="ExternalSourceError: boom")
    v = evaluate(o, {"expect_title_any": ["palace"], "forbid_empty": True})
    # 에러면 recall 미적용·빈결과 위반도 달지 않는다(측정 불가로 분리).
    assert not v.recall_applicable
    assert not any("0 results" in m for m in v.violations)
    assert not v.clean  # error 자체로 clean 아님


def test_percentile_nearest_rank():
    vals = [10, 20, 30, 40, 50]
    assert _percentile(vals, 50) == 30
    assert _percentile(vals, 95) == 50
    assert _percentile([], 50) is None
    assert _percentile([42.0], 95) == 42.0


def test_aggregate_rates_and_denominators():
    verdicts = [
        evaluate(
            _outcome(
                query_id="a",
                titles=["Palace"],
                statuses=["fits"],
                considered=8,
                excluded_hard=4,
            ),
            {"expect_title_any": ["palace"], "forbid_empty": True},
        ),
        evaluate(
            _outcome(query_id="b", titles=[], statuses=[]),
            {"expect_title_any": ["temple"], "forbid_empty": True},
        ),  # empty + recall miss + violation
        evaluate(
            _outcome(query_id="c", titles=["X"], statuses=["alternative"]), {}
        ),  # no expectation
        evaluate(
            _outcome(query_id="d", error="X: y"), {"expect_title_any": ["z"]}
        ),  # error
    ]
    report = aggregate(verdicts)
    assert report.total == 4
    assert report.errors == 1
    # recall 모수 = 기대 있고 에러 아닌 것(a, b) = 2, hit=1 → 0.5
    assert report.recall_denominator == 2
    assert report.recall_at_k == 0.5
    # empty_rate 모수 = 에러 제외 3개(a,b,c) 중 b 1개 = 1/3
    assert abs(report.empty_rate - (1 / 3)) < 1e-9
    # 위반: b(빈결과) = 1 / 3 (에러 제외 모수)
    assert abs(report.constraint_violation_rate - (1 / 3)) < 1e-9


def test_report_as_dict_rounds_and_nulls():
    v = evaluate(
        _outcome(titles=["A"], statuses=["fits"], considered=8, excluded_hard=1), {}
    )
    d = aggregate([v]).as_dict()
    assert d["total"] == 1
    assert d["queries"][0]["recall_hit"] is None  # 기대 없음
    assert d["queries"][0]["fits_ratio"] == 1.0
