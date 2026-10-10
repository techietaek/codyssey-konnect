"""chat_messages 영속 (Phase 2 L4 — 챗봇 Long-term memory).

정식 로그인 사용자의 대화 턴을 저장/복구/초기화한다. user_id 는 호출부가 **검증된 JWT
에서** 넘긴다(라우터에서 바인딩). 여기선 그 id 로만 읽고 쓴다. supabase-py 는 동기 →
asyncio.to_thread 로 감싼다. 세션(sessions.py)·선호(preferences.py)와 분리한다.

저장 content 는 대화 라우팅 맥락 텍스트일 뿐, 외부 API 사실 필드가 아니다(캐싱 금지
규약과 무관 — 사실은 매 요청 라이브 재조회). (migrations/0003_chat_messages.sql)
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.exceptions import SystemError
from app.db.client import get_client
from app.models.chat import ChatTurn

_TABLE = "chat_messages"


async def get_messages(user_id: str) -> list[ChatTurn]:
    """해당 user 의 전체 누적 대화를 시간순으로(복구용). 없으면 빈 리스트."""

    def _q() -> list[dict[str, Any]]:
        res = (
            get_client()
            .table(_TABLE)
            .select("role,content,created_at")
            .eq("user_id", user_id)
            .order("created_at")
            .order("id")  # 같은 ms 내 삽입 순서 보존(user→assistant)
            .execute()
        )
        return res.data or []

    try:
        rows = await asyncio.to_thread(_q)
    except Exception as e:
        raise SystemError("Could not load your conversation.") from e
    return [ChatTurn(role=r["role"], content=r["content"]) for r in rows]


async def append_messages(user_id: str, turns: list[ChatTurn]) -> None:
    """대화 턴들을 추가(append-only 로그). 빈 리스트면 no-op."""
    if not turns:
        return
    payload = [
        {"user_id": user_id, "role": t.role, "content": t.content} for t in turns
    ]

    def _q() -> None:
        get_client().table(_TABLE).insert(payload).execute()

    try:
        await asyncio.to_thread(_q)
    except Exception as e:
        raise SystemError("Could not save your conversation.") from e


async def clear_messages(user_id: str) -> None:
    """해당 user 의 대화 전체 삭제(Clear chat 초기화)."""

    def _q() -> None:
        get_client().table(_TABLE).delete().eq("user_id", user_id).execute()

    try:
        await asyncio.to_thread(_q)
    except Exception as e:
        raise SystemError("Could not clear your conversation.") from e
