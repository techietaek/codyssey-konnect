"""P1 적응형 반경 ladder (collect_judged) 유닛테스트 — 외부 I/O 모킹.

유효 후보가 min_viable 미만이면 반경을 넓혀 재조회하고, 충분하면 확장하지 않음을 검증한다.
_fetch_pool·_enrich·semantic_similarities 를 orchestrator 네임스페이스에서 monkeypatch 한다
(tools 와 동일 패턴 — 모듈이 import 시점에 헬퍼를 바인딩).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.agent import orchestrator as orch
from app.agent.context import RequestContext
from app.core.trace import Trace
from app.domain.budget import BudgetVerdict
from app.domain.timing import TimingVerdict
from app.models.recommend import (
    Candidate,
    ParsedConditions,
    ResultStatus,
    StartLocation,
)


def _ctx() -> RequestContext:
    return RequestContext(
        start_location=StartLocation(label="x", lat=37.57, lng=126.98),
        start_at=datetime(2026, 10, 15, 13, 0),
        end_at=datetime(2026, 10, 15, 18, 0),
    )


def _valid(cid: str, distance_m: int | None = None):
    cand = Candidate(
        id=cid,
        title=f"P{cid}",
        status=ResultStatus.FITS,
        lat=37.57,
        lng=126.98,
        distance_m=distance_m,
    )
    return (cand, TimingVerdict.OPEN, BudgetVerdict.UNKNOWN, f"P{cid}")


def _hard():
    return (None, TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN, "")


async def _zeros(texts, intent, trace):
    return [0.0] * len(texts)


def test_expands_when_thin(monkeypatch):
    # radius0 풀의 1개는 Hard 제외(0 valid) → min_viable(2) 미만 → 반경 확대.
    first_pool = [{"contentid": "a"}]

    async def fake_fetch(lat, lng, trace, on_date, radius):
        assert radius == 3000  # 첫 확장 단계
        return [{"contentid": "b"}, {"contentid": "c"}]

    async def fake_enrich(item, ctx, cond, trace):
        cid = item["contentid"]
        return _hard() if cid == "a" else _valid(cid, distance_m=2300)

    monkeypatch.setattr(orch, "_fetch_pool", fake_fetch)
    monkeypatch.setattr(orch, "semantic_similarities", _zeros)
    monkeypatch.setattr(orch, "_enrich", fake_enrich)

    judged, hard, used = asyncio.run(
        orch.collect_judged(
            37.57,
            126.98,
            _ctx(),
            ParsedConditions(),
            Trace(),
            first_pool=first_pool,
            enrich_pool=8,
        )
    )
    assert len(judged) == 2
    assert hard == 1  # item a
    assert used == 3000
    # 확대로 편입된 후보는 거리 라벨 표시용으로 태깅되고 직선거리를 갖는다.
    assert all(c.from_widened_search for (c, *_) in judged)
    assert all(c.distance_m == 2300 for (c, *_) in judged)


def test_first_tier_candidates_not_flagged_widened(monkeypatch):
    # 1단계(1500m)에서 충족된 후보는 widened 아님(거리 라벨 미표시).
    async def fake_enrich(item, ctx, cond, trace):
        return _valid(item["contentid"], distance_m=400)

    monkeypatch.setattr(orch, "semantic_similarities", _zeros)
    monkeypatch.setattr(orch, "_enrich", fake_enrich)
    judged, _h, used = asyncio.run(
        orch.collect_judged(
            37.57,
            126.98,
            _ctx(),
            ParsedConditions(),
            Trace(),
            first_pool=[{"contentid": "b"}, {"contentid": "c"}],
            enrich_pool=8,
        )
    )
    assert used == 1500
    assert not any(c.from_widened_search for (c, *_) in judged)


def test_no_expand_when_enough(monkeypatch):
    first_pool = [{"contentid": "b"}, {"contentid": "c"}]
    calls = {"fetch": 0}

    async def fake_fetch(*a, **k):
        calls["fetch"] += 1
        return []

    async def fake_enrich(item, ctx, cond, trace):
        return _valid(item["contentid"])

    monkeypatch.setattr(orch, "_fetch_pool", fake_fetch)
    monkeypatch.setattr(orch, "semantic_similarities", _zeros)
    monkeypatch.setattr(orch, "_enrich", fake_enrich)

    judged, _hard, used = asyncio.run(
        orch.collect_judged(
            37.57,
            126.98,
            _ctx(),
            ParsedConditions(),
            Trace(),
            first_pool=first_pool,
            enrich_pool=8,
        )
    )
    assert len(judged) == 2 and used == 1500
    assert calls["fetch"] == 0  # 확장 재조회 없음(밀집 → 지연 불변)


def test_expands_to_last_radius_then_stops(monkeypatch):
    # 끝까지 희소해도 ladder 끝에서 멈춘다(무한 아님). 각 단계 새 아이템 1개씩.
    pools = {3000: [{"contentid": "b"}], 5000: [{"contentid": "c"}]}

    async def fake_fetch(lat, lng, trace, on_date, radius):
        return pools.get(radius, [])

    async def fake_enrich(item, ctx, cond, trace):
        return _hard()  # 전부 Hard → 끝까지 0 valid

    monkeypatch.setattr(orch, "_fetch_pool", fake_fetch)
    monkeypatch.setattr(orch, "semantic_similarities", _zeros)
    monkeypatch.setattr(orch, "_enrich", fake_enrich)

    judged, hard, used = asyncio.run(
        orch.collect_judged(
            37.57,
            126.98,
            _ctx(),
            ParsedConditions(),
            Trace(),
            first_pool=[{"contentid": "a"}],
            enrich_pool=8,
        )
    )
    assert judged == []
    assert used == 5000  # 마지막 단계까지 확장 후 종료
    assert hard == 3  # a, b, c
