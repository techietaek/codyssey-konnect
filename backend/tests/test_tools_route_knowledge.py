"""walk_route / plan_day_route / answer_knowledge tool 경계 테스트 (rollout 2b·2c).

Tmap·RAG·루트조립은 monkeypatch 로 격리하고, tool 이 leg 구성·graceful·위임을 바르게
하는지 본다. tool 은 import 시점 바인딩 → 각 tool 모듈 네임스페이스를 패치.
"""

from __future__ import annotations

import asyncio

from app.agent.tools import knowledge as kn
from app.agent.tools import route as rt
from app.core.trace import Trace
from app.models.rag import RagAnswer
from app.models.recommend import Provenance


def _leg(lat_dist):
    return {"walk_minutes": 7, "distance_m": lat_dist, "path": [[37.0, 127.0]]}


def test_walk_route_non_sequential_legs_from_origin(monkeypatch):
    calls = []

    async def fake_route(ox, oy, dx, dy):
        calls.append((ox, oy, dx, dy))
        return _leg(500)

    monkeypatch.setattr(rt.tmap, "pedestrian_route", fake_route)
    out = asyncio.run(
        rt.walk_route((37.5, 127.0), [(37.6, 127.1), (37.7, 127.2)], Trace())
    )
    assert len(out) == 2
    assert all(m.walk_minutes == 7 and m.provenance is Provenance.ESTIMATE for m in out)
    # 모든 leg 가 origin 에서 출발
    assert calls[0][:2] == (37.5, 127.0) and calls[1][:2] == (37.5, 127.0)


def test_walk_route_sequential_chains_stops(monkeypatch):
    calls = []

    async def fake_route(ox, oy, dx, dy):
        calls.append((ox, oy, dx, dy))
        return _leg(300)

    monkeypatch.setattr(rt.tmap, "pedestrian_route", fake_route)
    asyncio.run(
        rt.walk_route(
            (37.5, 127.0), [(37.6, 127.1), (37.7, 127.2)], Trace(), sequential=True
        )
    )
    # leg2 는 stop1 에서 출발(연쇄)
    assert calls[1][:2] == (37.6, 127.1)


def test_walk_route_failed_leg_is_unavailable(monkeypatch):
    async def fake_route(ox, oy, dx, dy):
        return None  # Tmap 실패

    monkeypatch.setattr(rt.tmap, "pedestrian_route", fake_route)
    out = asyncio.run(rt.walk_route((37.5, 127.0), [(37.6, 127.1)], Trace()))
    assert out[0].walk_minutes is None
    assert out[0].display == "Route unavailable"
    assert out[0].provenance is Provenance.UNCONFIRMED


def test_walk_route_empty_stops():
    assert asyncio.run(rt.walk_route((37.5, 127.0), [], Trace())) == []


def test_plan_day_route_delegates(monkeypatch):
    class _StubRoute:
        stops = [1, 2]

    stub = _StubRoute()

    async def fake_build(origin, stops, start_at, avail, trace):
        return stub

    monkeypatch.setattr(rt, "_build_route", fake_build)
    out = asyncio.run(rt.plan_day_route("ORIGIN", [], None, 300, Trace()))
    assert out is stub


def test_plan_day_route_none_when_infeasible(monkeypatch):
    async def fake_build(origin, stops, start_at, avail, trace):
        return None  # 창 초과 → 루트 불가

    monkeypatch.setattr(rt, "_build_route", fake_build)
    assert asyncio.run(rt.plan_day_route("ORIGIN", [], None, 60, Trace())) is None


def test_answer_knowledge_delegates(monkeypatch):
    async def fake_answer(q, trace):
        return RagAnswer(answer=f"A:{q}", grounded=True)

    monkeypatch.setattr(kn, "answer_question", fake_answer)
    out = asyncio.run(kn.answer_knowledge("how to pay subway", Trace()))
    assert out.grounded and out.answer == "A:how to pay subway"
