"""세션 영속 테스트 (Phase 2 L1c) — 인증 게이팅 + 부분 갱신 no-op (DB 미접근)."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.db import sessions
from app.main import app

client = TestClient(app)


def test_get_session_requires_auth():
    r = client.get("/api/session")
    assert r.status_code == 401
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "auth_error"


def test_put_session_requires_auth():
    r = client.put("/api/session", json={"current_choice": {"candidateId": "x"}})
    assert r.status_code == 401
    assert r.json()["ok"] is False


def test_upsert_noop_when_no_allowed_fields(monkeypatch):
    # 허용 필드가 없으면 DB 클라이언트를 건드리지 않는다(no-op).
    def _boom():
        raise AssertionError("get_client should not be called on no-op")

    monkeypatch.setattr(sessions, "get_client", _boom)
    asyncio.run(sessions.upsert_session("user-1", {}))
    asyncio.run(sessions.upsert_session("user-1", {"unknown": 1}))  # 허용 외 → 무시
