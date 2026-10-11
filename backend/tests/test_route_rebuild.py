"""저장 루트 다시보기(pin_titles) API 배선 + current_route 세션 필드 테스트.

외부 API/LLM 미접근 — recommend_route·DB 클라이언트를 모킹해 배선만 검증.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.api import route as route_api
from app.db import sessions
from app.main import app
from app.models.route import RouteData

client = TestClient(app)


def test_route_rebuild_pins_and_caps(monkeypatch):
    # pin_titles 가 오면 recommend_route 에 pin_titles + max_stops(=len) + want_more 로 전달.
    captured = {}

    async def fake_route(ctx, trace, *a, **kw):
        captured.update(kw)
        return RouteData(routes=[], origin=None)

    monkeypatch.setattr(route_api, "recommend_route", fake_route)
    r = client.post(
        "/api/route",
        json={
            "start_location": {"label": "Gwanghwamun", "lat": 37.57, "lng": 126.98},
            "start_at": "2026-10-11T10:00:00",
            "end_at": "2026-10-11T14:00:00",
            "pin_titles": ["A", "B", "C"],
        },
    )
    assert r.status_code == 200
    assert captured.get("pin_titles") == ["A", "B", "C"]
    assert captured.get("max_stops") == 3
    assert captured.get("want_more") is True


def test_route_without_pins_is_normal(monkeypatch):
    captured = {}

    async def fake_route(ctx, trace, *a, **kw):
        captured.update(kw)
        return RouteData(routes=[], origin=None)

    monkeypatch.setattr(route_api, "recommend_route", fake_route)
    r = client.post(
        "/api/route",
        json={
            "start_location": {"label": "Gwanghwamun", "lat": 37.57, "lng": 126.98},
            "start_at": "2026-10-11T10:00:00",
            "end_at": "2026-10-11T14:00:00",
        },
    )
    assert r.status_code == 200
    assert captured.get("pin_titles") is None
    assert captured.get("max_stops") is None
    assert captured.get("want_more") is False


def test_upsert_allows_current_route(monkeypatch):
    # current_route 는 허용 필드 → DB upsert payload 에 포함된다.
    seen = {}

    class _Tbl:
        def upsert(self, payload):
            seen.update(payload)
            return self

        def execute(self):
            return None

    class _Client:
        def table(self, _name):
            return _Tbl()

    monkeypatch.setattr(sessions, "get_client", lambda: _Client())
    asyncio.run(
        sessions.upsert_session("user-1", {"current_route": {"stops": ["A", "B"]}})
    )
    assert seen.get("current_route") == {"stops": ["A", "B"]}
    assert seen.get("user_id") == "user-1"
