"""검색 품질 지표 — 순수 집계(네트워크·LLM 무관, 유닛테스트 대상).

runner 가 라이브 실행으로 만든 `QueryOutcome`(사실만)을 받아, 골든 기대값과 대조해
per-query 판정(`QueryVerdict`)과 전체 집계(`EvalReport`)를 낸다. 여기엔 외부 I/O 가 없다.

지표 정의:
- recall@k        : 기대(expect_title_any)가 있는 쿼리 중, 상위 결과 제목에 기대가 잡힌 비율.
- constraint 위반 : 금지 제목 노출 / 비어있으면 안 되는데 0건 / 구조 불변식 위반 중 하나라도.
- empty_rate      : 0건 반환 비율.
- hard_exclude    : trace judge 단계의 excluded_hard / considered (검색 후 가용성에서 걸러진 비율).
- fits_ratio      : 반환 후보 중 status=fits 비율.
- 지연            : p50/p95 (ms).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QueryOutcome:
    """한 쿼리의 라이브 실행 결과(사실만 — 판정은 evaluate 가 한다)."""

    query_id: str
    mode: str  # "recommend" | "route"
    titles: list[str]  # 반환 후보(A)·스톱(B) 제목
    statuses: list[str]  # 각 후보 status 값
    latency_ms: float
    considered: int | None = None  # trace: 판정에 넣은 후보 수
    excluded_hard: int | None = None  # trace: Hard 제외 수
    extra_invariant_errors: list[str] = field(default_factory=list)  # 구조 불변식 위반
    error: str | None = None  # 실행 예외(있으면 그 쿼리는 실패로 집계)

    @property
    def returned(self) -> int:
        return len(self.titles)

    @property
    def empty(self) -> bool:
        return self.returned == 0


@dataclass
class QueryVerdict:
    """골든 기대값 대조 결과(per-query)."""

    query_id: str
    mode: str
    returned: int
    empty: bool
    recall_applicable: bool  # 기대(expect_title_any)가 있었는가
    recall_hit: bool  # 기대가 결과에 잡혔는가
    violations: list[str]  # 위반 사유(금지 제목·빈결과·구조 불변식). 비면 clean.
    fits_ratio: float | None
    hard_exclude_rate: float | None
    latency_ms: float
    error: str | None = None

    @property
    def clean(self) -> bool:
        return not self.violations and self.error is None


def _ci_contains_any(haystacks: list[str], needles: list[str]) -> bool:
    """needles 중 하나라도 haystacks 어느 제목의 부분문자열이면 True(대소문자 무시)."""
    lows = [h.lower() for h in haystacks]
    return any(n.lower() in h for n in needles for h in lows)


def _matched_titles(titles: list[str], needles: list[str]) -> list[str]:
    """needles 중 하나라도 포함하는 제목들(위반 보고용)."""
    lows = [(t, t.lower()) for t in titles]
    return [t for t, low in lows if any(n.lower() in low for n in needles)]


def evaluate(outcome: QueryOutcome, golden: dict) -> QueryVerdict:
    """한 outcome 을 골든 쿼리 기대값과 대조 → QueryVerdict.

    golden 키: expect_title_any(list), forbid_title_any(list), forbid_empty(bool).
    구조 불변식 위반은 outcome.extra_invariant_errors 로 이미 들어온다(runner 가 채운다).
    """
    expect = golden.get("expect_title_any") or []
    forbid = golden.get("forbid_title_any") or []
    forbid_empty = bool(golden.get("forbid_empty"))

    violations = list(outcome.extra_invariant_errors)
    if forbid:
        hit = _matched_titles(outcome.titles, forbid)
        if hit:
            violations.append(f"forbidden title present: {hit}")
    if forbid_empty and outcome.empty and outcome.error is None:
        violations.append("returned 0 results but this query should not be empty")

    recall_applicable = bool(expect) and outcome.error is None
    recall_hit = recall_applicable and _ci_contains_any(outcome.titles, expect)

    fits_ratio = (
        sum(1 for s in outcome.statuses if s == "fits") / outcome.returned
        if outcome.returned
        else None
    )
    # 루트 모드는 considered 는 있어도 excluded_hard 를 분리 보고하지 않아 None → rate 생략.
    hard_rate = (
        outcome.excluded_hard / outcome.considered
        if outcome.considered and outcome.excluded_hard is not None
        else None
    )

    return QueryVerdict(
        query_id=outcome.query_id,
        mode=outcome.mode,
        returned=outcome.returned,
        empty=outcome.empty,
        recall_applicable=recall_applicable,
        recall_hit=recall_hit,
        violations=violations,
        fits_ratio=fits_ratio,
        hard_exclude_rate=hard_rate,
        latency_ms=outcome.latency_ms,
        error=outcome.error,
    )


def _percentile(values: list[float], pct: float) -> float | None:
    """선형보간 없는 nearest-rank 백분위(작은 N 에서 직관적). 빈 리스트는 None."""
    if not values:
        return None
    ordered = sorted(values)
    # nearest-rank: ceil(pct/100 * N) 번째(1-indexed)
    rank = max(1, -(-int(pct) * len(ordered) // 100))  # ceil division
    return ordered[min(rank, len(ordered)) - 1]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


@dataclass
class EvalReport:
    """전체 집계. run_eval 가 콘솔·JSON 으로 렌더."""

    total: int
    errors: int
    empty_rate: float
    recall_at_k: float | None  # 기대가 있는 쿼리에 한정
    recall_denominator: int  # 그 쿼리 수
    constraint_violation_rate: float  # clean 하지 않은 쿼리 비율(에러 제외 모수)
    mean_fits_ratio: float | None
    mean_hard_exclude_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    verdicts: list[QueryVerdict]

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "errors": self.errors,
            "empty_rate": round(self.empty_rate, 4),
            "recall_at_k": (
                None if self.recall_at_k is None else round(self.recall_at_k, 4)
            ),
            "recall_denominator": self.recall_denominator,
            "constraint_violation_rate": round(self.constraint_violation_rate, 4),
            "mean_fits_ratio": (
                None if self.mean_fits_ratio is None else round(self.mean_fits_ratio, 4)
            ),
            "mean_hard_exclude_rate": (
                None
                if self.mean_hard_exclude_rate is None
                else round(self.mean_hard_exclude_rate, 4)
            ),
            "latency_p50_ms": (
                None if self.latency_p50_ms is None else round(self.latency_p50_ms, 1)
            ),
            "latency_p95_ms": (
                None if self.latency_p95_ms is None else round(self.latency_p95_ms, 1)
            ),
            "queries": [
                {
                    "id": v.query_id,
                    "mode": v.mode,
                    "returned": v.returned,
                    "recall_hit": v.recall_hit if v.recall_applicable else None,
                    "violations": v.violations,
                    "fits_ratio": (
                        None if v.fits_ratio is None else round(v.fits_ratio, 3)
                    ),
                    "hard_exclude_rate": (
                        None
                        if v.hard_exclude_rate is None
                        else round(v.hard_exclude_rate, 3)
                    ),
                    "latency_ms": round(v.latency_ms, 1),
                    "error": v.error,
                }
                for v in self.verdicts
            ],
        }


def aggregate(verdicts: list[QueryVerdict]) -> EvalReport:
    """per-query 판정 → 전체 집계. 에러 쿼리는 지표 모수에서 합리적으로 제외한다."""
    total = len(verdicts)
    errors = sum(1 for v in verdicts if v.error is not None)
    ok = [v for v in verdicts if v.error is None]  # 지연·0건·위반 모수

    empty_rate = (sum(1 for v in ok if v.empty) / len(ok)) if ok else 0.0

    recall_pool = [v for v in ok if v.recall_applicable]
    recall_at_k = (
        sum(1 for v in recall_pool if v.recall_hit) / len(recall_pool)
        if recall_pool
        else None
    )

    violation_rate = sum(1 for v in ok if v.violations) / len(ok) if ok else 0.0

    fits = [v.fits_ratio for v in ok if v.fits_ratio is not None]
    hard = [v.hard_exclude_rate for v in ok if v.hard_exclude_rate is not None]
    lat = [v.latency_ms for v in ok]

    return EvalReport(
        total=total,
        errors=errors,
        empty_rate=empty_rate,
        recall_at_k=recall_at_k,
        recall_denominator=len(recall_pool),
        constraint_violation_rate=violation_rate,
        mean_fits_ratio=_mean(fits),
        mean_hard_exclude_rate=_mean(hard),
        latency_p50_ms=_percentile(lat, 50),
        latency_p95_ms=_percentile(lat, 95),
        verdicts=verdicts,
    )
