"""검색 품질 Eval 하네스 (P0, docs/recommendation-and-search-quality.md §7).

추천 A/B 를 골든 쿼리셋으로 돌려 recall@k·constraint 위반율·0건율·Hard 제외율·
지연(p50/p95)을 측정한다. 모든 검색 품질 개선(P1~P6)의 before/after 를 이 지표로 A/B.

- `golden_set.json` : 쿼리셋(Product 도 편집 가능한 JSON).
- `metrics.py`      : 순수 집계 함수(네트워크 무관, 유닛테스트 대상).
- `runner.py`       : 라이브 실행(recommend_a/route) → QueryOutcome + trace 신호.
- `run_eval.py`     : CLI 엔트리(`python -m app.eval.run_eval`).

신뢰 경계: eval 은 '측정만' 한다 — 추천 로직·판정에 전혀 관여하지 않는다.
"""
