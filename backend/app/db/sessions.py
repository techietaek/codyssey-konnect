"""user_sessions 영속 (Phase 2 L1c).

user_id 는 호출부가 **검증된 JWT 에서** 넘긴다(라우터에서 바인딩). 여기선 그 id 로만
읽고 쓴다. supabase-py 는 동기 → asyncio.to_thread 로 감싼다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import SystemError
from app.db.client import get_client

_TABLE = "user_sessions"


async def get_session(user_id: str) -> dict[str, Any] | None:
    """해당 user 의 세션 행(없으면 None)."""

    def _q() -> dict[str, Any] | None:
        res = (
            get_client()
            .table(_TABLE)
            .select("last_request,current_choice,updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None

    try:
        return await asyncio.to_thread(_q)
    except SystemError:
        raise
    except Exception as e:
        raise SystemError("Could not load your saved session.") from e


async def upsert_session(user_id: str, fields: dict[str, Any]) -> None:
    """제공된 필드만 upsert(부분 갱신). 빈 fields 면 no-op."""
    allowed = {
        k: v for k, v in fields.items() if k in ("last_request", "current_choice")
    }
    if not allowed:
        return
    payload = {
        "user_id": user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **allowed,
    }

    def _q() -> None:
        get_client().table(_TABLE).upsert(payload).execute()

    try:
        await asyncio.to_thread(_q)
    except SystemError:
        raise
    except Exception as e:
        raise SystemError("Could not save your session.") from e
