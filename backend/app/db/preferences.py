"""user_preferences 영속 (Phase 2 L2 · P-09).

user_id 는 호출부가 **검증된 JWT 에서** 넘긴다(라우터에서 바인딩). 여기선 그 id 로만
읽고 쓴다. supabase-py 는 동기 → asyncio.to_thread 로 감싼다.
세션(sessions.py)과 분리 — 임시 상태를 장기 선호로 자동승격하지 않는다(FR-L5).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import SystemError
from app.db.client import get_client

_TABLE = "user_preferences"


async def get_preferences(user_id: str) -> dict[str, Any] | None:
    """해당 user 의 선호 행(없으면 None → 아직 온보딩 전)."""

    def _q() -> dict[str, Any] | None:
        res = (
            get_client()
            .table(_TABLE)
            .select("interests,prefer_shorter_walks,onboarded_at,updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    try:
        return await asyncio.to_thread(_q)
    except Exception as e:
        raise SystemError("Could not load your preferences.") from e


async def upsert_preferences(
    user_id: str, interests: list[str], prefer_shorter_walks: bool | None
) -> None:
    """선호 전체 치환(Save·Skip·초기화 공용). 저장 시 onboarded_at 을 찍어 재노출 방지.

    세션의 부분 갱신과 달리 선호는 '사용자가 확정한 현재 상태' 전체를 치환한다
    (미선택=빈 리스트/None 그대로 저장 — 빈값을 긍정 기본값으로 바꾸지 않음).
    """
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": user_id,
        "interests": interests,
        "prefer_shorter_walks": prefer_shorter_walks,
        "onboarded_at": now,
        "updated_at": now,
    }

    def _q() -> None:
        get_client().table(_TABLE).upsert(payload).execute()

    try:
        await asyncio.to_thread(_q)
    except Exception as e:
        raise SystemError("Could not save your preferences.") from e
