"""단일 챗봇 Agent 라우터 (AG-1/2) — POST /api/chat + 대화 영속(L4).

자연어 메시지를 tool-calling Agent 로 라우팅해 FAQ 답변 / 추천 / 되묻기를 통합 반환한다.
얇게 유지 — 라우팅·실행은 agent/chat_agent, 검색·판정은 rag/·domain/ 가 소유.
로그인 사용자면 저장 선호를 Soft 신호로 전달(추천 tool 경로에서만 반영).

Long-term memory(L4): 정식 로그인 사용자는 대화 턴을 영속한다 — 재접근·기기 간 복구
(GET /history)와 멀티턴 맥락 재주입(저장된 턴을 라우팅 맥락의 정본으로 로드)에 쓴다.
익명/비로그인은 기존대로 세션 내 메모리(클라이언트 history)로만 동작(영속 없음).
저장 content 는 라우팅 맥락 텍스트일 뿐 사실 캐시가 아니다(캐싱 금지 규약과 무관).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.agent_loop import run_chat_loop
from app.agent.chat_agent import run_chat
from app.config import settings
from app.core.auth import AuthUser, get_current_user, get_optional_user
from app.core.trace import Trace
from app.db.chat import append_messages, clear_messages, get_messages
from app.db.preferences import get_preferences
from app.models.chat import (
    ChatHistory,
    ChatRequest,
    ChatResponse,
    ChatTurn,
    summarize_response,
)
from app.models.envelope import Envelope
from app.models.recommend import InterestCode

logger = logging.getLogger("konnect.chat")

router = APIRouter(prefix="/api", tags=["chat"])


def _persists(user: AuthUser | None) -> bool:
    """대화를 영속하는 대상인가 — 정식 로그인(비익명)만(제품 결정 L4)."""
    return bool(user and not user.is_anonymous)


@router.post("/chat", response_model=Envelope[ChatResponse])
async def chat(
    req: ChatRequest,
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> Envelope[ChatResponse]:
    trace = Trace()
    trace.step(
        "auth",
        user=user.id if user else None,
        anonymous=bool(user and user.is_anonymous),
    )

    saved_interests: list[InterestCode] | None = None
    prefer_shorter_walks: bool | None = None
    saved_open_preferences: list[str] | None = None
    if user is not None:
        pref = await get_preferences(user.id)
        if pref:
            saved_interests = [InterestCode(i) for i in (pref.get("interests") or [])]
            prefer_shorter_walks = pref.get("prefer_shorter_walks")
            saved_open_preferences = pref.get("open_preferences") or []

    # 멀티턴 맥락: 정식 로그인은 저장된 대화를 정본으로(기기 간 연속성) — 실패 시 클라이언트
    # history 로 graceful fallback. 익명/비로그인은 클라이언트가 보낸 history 그대로.
    history: list[ChatTurn] = req.history
    if _persists(user):
        try:
            history = await get_messages(user.id)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001 — 저장소 문제가 대화를 막지 않게
            logger.warning("chat history load failed: %s", type(e).__name__)
            trace.step("chat_history_load", error=type(e).__name__)

    # agentic while-loop(§6) on/off — off 면 기존 단일 라우팅(fallback).
    chat_fn = run_chat_loop if settings.agent_loop else run_chat
    data = await chat_fn(
        req.message,
        req.context,
        trace,
        saved_interests,
        prefer_shorter_walks,
        saved_open_preferences,
        history,
    )
    # 이 턴의 맥락 요약(프론트 로컬 history·영속 저장 공용) — 사실 재서술 아님.
    data.history_summary = summarize_response(data)

    # 영속(정식 로그인만): 사용자 발화 + 어시스턴트 요약 2턴 append. 실패해도 응답은 그대로.
    if _persists(user):
        try:
            await append_messages(
                user.id,  # type: ignore[union-attr]
                [
                    ChatTurn(role="user", content=req.message),
                    ChatTurn(role="assistant", content=data.history_summary),
                ],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("chat history save failed: %s", type(e).__name__)
            trace.step("chat_history_save", error=type(e).__name__)

    return Envelope.success(data=data, trace_id=trace.trace_id)


@router.get("/chat/history", response_model=Envelope[ChatHistory])
async def read_history(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Envelope[ChatHistory]:
    """정식 로그인 사용자의 전체 누적 대화를 복구용으로 반환(익명은 빈 리스트)."""
    trace = Trace()
    turns = await get_messages(user.id) if _persists(user) else []
    return Envelope.success(data=ChatHistory(turns=turns), trace_id=trace.trace_id)


@router.delete("/chat/history", response_model=Envelope[ChatHistory])
async def delete_history(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> Envelope[ChatHistory]:
    """Clear chat — 대화 전체 초기화. 정식 로그인만(익명은 no-op)."""
    trace = Trace()
    if _persists(user):
        await clear_messages(user.id)
    return Envelope.success(data=ChatHistory(turns=[]), trace_id=trace.trace_id)
