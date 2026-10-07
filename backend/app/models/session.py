"""세션 영속 입출력 스키마 (Phase 2 L1c)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SessionState(BaseModel):
    """저장된 세션 상태(GET 응답). 없으면 전부 None."""

    last_request: dict[str, Any] | None = None
    current_choice: dict[str, Any] | None = None
    updated_at: str | None = None


class SessionUpdate(BaseModel):
    """세션 부분 갱신(PUT). 제공된 필드만 저장(exclude_unset)."""

    last_request: dict[str, Any] | None = None
    current_choice: dict[str, Any] | None = None
