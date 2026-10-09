"""골든 쿼리 라이브 실행 → QueryOutcome (사실만). 판정·집계는 metrics 가 한다.

추천 A/B 를 실제 공식 API 로 호출해(캐싱 없음·라이브) 제목·상태·지연·trace 신호를 모은다.
한 쿼리 실패가 전체 eval 을 막지 않게 per-query graceful — 예외는 outcome.error 로 담는다.

주의: 추천 로직에 전혀 관여하지 않는다 — 측정 전용(신뢰 경계 밖에서 관찰만).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agent.context import RequestContext
from app.core.trace import Trace
from app.eval.metrics import QueryOutcome
from app.models.recommend import StartLocation

GOLDEN_PATH = Path(__file__).with_name("golden_set.json")


def load_golden(path: Path | None = None) -> list[dict]:
    """골든 쿼리셋 로드. queries 배열만 반환."""
    data = json.loads((path or GOLDEN_PATH).read_text(encoding="utf-8"))
    return data.get("queries", [])


def _ctx(q: dict) -> RequestContext:
    s = q["start"]
    return RequestContext(
        start_location=StartLocation(
            label=s.get("label", ""), lat=s.get("lat"), lng=s.get("lng")
        ),
        start_at=datetime.fromisoformat(q["start_at"]),
        end_at=datetime.fromisoformat(q["end_at"]),
        note=q.get("note"),
    )


def _find_step(trace: Trace, name: str) -> dict[str, Any] | None:
    """trace 에서 특정 step 의 마지막 기록을 찾는다(없으면 None)."""
    for entry in reversed(trace.steps):
        if entry.get("step") == name:
            return entry
    return None


def _recommend_invariants(data: Any) -> list[str]:
    """추천 A 구조 불변식(드리프트 독립) — 위반 사유 문자열 리스트."""
    errs: list[str] = []
    cands = data.candidates
    if len(cands) > 4:
        errs.append(f"candidates={len(cands)} exceeds max 4")
    valid_status = {"fits", "alternative", "check_needed"}
    bad = [c.status.value for c in cands if c.status.value not in valid_status]
    if bad:
        errs.append(f"leaked non-user status: {bad}")
    ids = [c.id for c in cands]
    if len(ids) != len(set(ids)):
        errs.append("duplicate candidate ids")
    if cands and (data.origin is None or data.origin.lat is None):
        errs.append("origin coords missing")
    return errs


def _route_invariants(data: Any) -> list[str]:
    """추천 B 구조 불변식 — 위반 사유 문자열 리스트.

    스톱 수는 '개수 제한이 아니라 시간창 허용분'이 Product 결정(domain/route.MAX_DAY_STOPS,
    강제 채움 금지). 따라서 하한 2 ~ 상한 MAX_DAY_STOPS 만 검사한다(과거 '2~3' 가정 아님).
    """
    from app.domain.route import MAX_DAY_STOPS

    errs: list[str] = []
    routes = data.routes
    if len(routes) > 1:
        errs.append(f"routes={len(routes)} (expected at most 1)")
    for r in routes:
        n = len(r.stops)
        if not (2 <= n <= MAX_DAY_STOPS):
            errs.append(f"route {r.id} has {n} stops (expected 2-{MAX_DAY_STOPS})")
        bad = [
            st.candidate.status.value
            for st in r.stops
            if st.candidate.status.value not in {"fits", "alternative", "check_needed"}
        ]
        if bad:
            errs.append(f"route stop leaked non-user status: {bad}")
    if not routes and not (data.unmet or "").strip():
        errs.append("empty routes but no unmet message")
    return errs


async def run_query(q: dict) -> QueryOutcome:
    """한 골든 쿼리를 라이브로 실행 → QueryOutcome. 예외는 graceful 로 담는다."""
    mode = q.get("mode", "recommend")
    trace = Trace()
    t0 = time.perf_counter()
    try:
        ctx = _ctx(q)
        if mode == "route":
            from app.agent.route_orchestrator import recommend_route

            data = await recommend_route(ctx, trace)
            latency = (time.perf_counter() - t0) * 1000
            titles = [st.candidate.title for r in data.routes for st in r.stops]
            statuses = [
                st.candidate.status.value for r in data.routes for st in r.stops
            ]
            feas = _find_step(trace, "route_feasible")
            # 루트는 hard/pref 제외가 trace 에서 분리 보고되지 않아(considered/feasible만)
            # hard_exclude 를 None 으로 둔다(과대보고 방지 — 정직성).
            return QueryOutcome(
                query_id=q["id"],
                mode=mode,
                titles=titles,
                statuses=statuses,
                latency_ms=latency,
                considered=(feas or {}).get("considered"),
                excluded_hard=None,
                extra_invariant_errors=_route_invariants(data),
            )

        from app.agent.orchestrator import recommend_a

        data = await recommend_a(ctx, trace)
        latency = (time.perf_counter() - t0) * 1000
        judge = _find_step(trace, "judge")
        return QueryOutcome(
            query_id=q["id"],
            mode=mode,
            titles=[c.title for c in data.candidates],
            statuses=[c.status.value for c in data.candidates],
            latency_ms=latency,
            considered=(judge or {}).get("considered"),
            excluded_hard=(judge or {}).get("excluded_hard"),
            extra_invariant_errors=_recommend_invariants(data),
        )
    except Exception as e:  # noqa: BLE001 — 한 쿼리 실패가 eval 전체를 막지 않는다
        latency = (time.perf_counter() - t0) * 1000
        return QueryOutcome(
            query_id=q.get("id", "?"),
            mode=mode,
            titles=[],
            statuses=[],
            latency_ms=latency,
            error=f"{type(e).__name__}: {e}",
        )
