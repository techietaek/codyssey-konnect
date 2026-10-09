"""검색 품질 Eval CLI — `python -m app.eval.run_eval`.

골든 쿼리셋을 라이브로 돌려(추천 A/B, 공식 API 직접 조회) 집계 지표를 콘솔에 찍고,
`--json PATH` 로 전체 결과를 저장한다. 모든 검색 품질 개선(P1~P6)의 before/after 를
이 리포트로 비교한다.

사용 예:
  python -m app.eval.run_eval                      # 전체 골든셋, 순차 실행
  python -m app.eval.run_eval --mode recommend     # 추천 A 만
  python -m app.eval.run_eval --filter a-gbg       # id 부분일치만
  python -m app.eval.run_eval --concurrency 3      # 병렬(지연 지표는 순차가 더 정확)
  python -m app.eval.run_eval --json eval_out.json # 결과 저장

주의: 라이브 조회라 OpenAI·TourAPI 키가 필요하다(캐싱 없음 — 매 실행 실제 호출).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.config import settings
from app.eval.metrics import EvalReport, aggregate, evaluate
from app.eval.runner import load_golden, run_query

# 라이브 실행에 사실상 필요한 키(없으면 대부분 쿼리가 error 로 떨어진다).
_REQUIRED_KEYS = ["openai_api_key", "data_go_kr_service_key"]
_OPTIONAL_KEYS = ["tmap_api_key", "google_places_api_key", "seoul_openapi_key"]


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _ms(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0f}ms"


def _print_report(report: EvalReport) -> None:
    print("\n" + "=" * 68)
    print("  KONNECT 검색 품질 Eval — 집계")
    print("=" * 68)
    print(f"  queries              : {report.total}  (errors: {report.errors})")
    print(
        f"  recall@k             : {_pct(report.recall_at_k)}"
        f"  (n={report.recall_denominator} with expectations)"
    )
    print(f"  empty_rate           : {_pct(report.empty_rate)}")
    print(f"  constraint_violation : {_pct(report.constraint_violation_rate)}")
    print(f"  mean fits_ratio      : {_pct(report.mean_fits_ratio)}")
    print(f"  mean hard_exclude    : {_pct(report.mean_hard_exclude_rate)}")
    print(
        f"  latency p50 / p95    : {_ms(report.latency_p50_ms)} / {_ms(report.latency_p95_ms)}"
    )
    print("-" * 68)
    print(f"  {'id':<26}{'mode':<10}{'ret':>4}{'recall':>8}{'lat':>8}  flags")
    print("-" * 68)
    for v in report.verdicts:
        recall = "—" if not v.recall_applicable else ("hit" if v.recall_hit else "MISS")
        flags = []
        if v.error:
            flags.append("ERROR")
        if v.violations:
            flags.append(f"{len(v.violations)} violation(s)")
        print(
            f"  {v.query_id:<26}{v.mode:<10}{v.returned:>4}{recall:>8}"
            f"{v.latency_ms:>7.0f}ms  {', '.join(flags)}"
        )
        for msg in v.violations:
            print(f"      ⚠ {msg}")
        if v.error:
            print(f"      ✗ {v.error}")
    print("=" * 68 + "\n")


async def _run(args: argparse.Namespace) -> EvalReport:
    queries = load_golden()
    if args.mode:
        queries = [q for q in queries if q.get("mode") == args.mode]
    if args.filter:
        queries = [q for q in queries if args.filter in q.get("id", "")]
    if not queries:
        raise SystemExit("No queries match the given filters.")

    if args.concurrency <= 1:
        outcomes = [await run_query(q) for q in queries]  # 순차 = 지연 지표 정확
    else:
        sem = asyncio.Semaphore(args.concurrency)

        async def _guarded(q: dict):
            async with sem:
                return await run_query(q)

        outcomes = await asyncio.gather(*(_guarded(q) for q in queries))

    by_id = {q["id"]: q for q in queries}
    verdicts = [evaluate(o, by_id[o.query_id]) for o in outcomes]
    return aggregate(verdicts)


def main() -> None:
    parser = argparse.ArgumentParser(description="KONNECT 검색 품질 Eval")
    parser.add_argument("--mode", choices=["recommend", "route"], help="한 모드만")
    parser.add_argument("--filter", help="쿼리 id 부분일치 필터")
    parser.add_argument(
        "--concurrency", type=int, default=1, help="병렬도(기본 1=순차, 지연 정확)"
    )
    parser.add_argument("--json", dest="json_out", help="결과 JSON 저장 경로")
    args = parser.parse_args()

    missing = settings.missing_keys(_REQUIRED_KEYS)
    if missing:
        print(f"⚠ 필수 키 누락: {missing} — 대부분 쿼리가 error 로 떨어질 수 있습니다.")
    opt_missing = settings.missing_keys(_OPTIONAL_KEYS)
    if opt_missing:
        print(f"ℹ 선택 키 누락(부분 기능): {opt_missing}")

    report = asyncio.run(_run(args))
    _print_report(report)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"→ 결과 저장: {args.json_out}")


if __name__ == "__main__":
    main()
