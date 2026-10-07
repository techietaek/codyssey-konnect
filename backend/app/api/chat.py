"""단일 챗봇 Agent 라우터 (AG-1/2) — POST /api/chat.

자연어 메시지를 tool-calling Agent 로 라우팅해 FAQ 답변 / 추천 / 되묻기를 통합 반환한다.
얇게 유지 — 라우팅·실행은 agent/chat_agent, 검색·판정은 rag/·domain/ 가 소유.
로그인 사용자면 저장 선호를 Soft 신호로 전달(추천 tool 경로에서만 반영).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.chat_agent import run_chat
from app.core.auth import AuthUser, get_optional_user
from app.core.trace import Trace
from app.db.preferences import get_preferences
from app.models.chat import ChatRequest, ChatResponse
from app.models.envelope import Envelope
from app.models.recommend import InterestCode

router = APIRouter(prefix="/api", tags=["chat"])


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
    if user is not None:
        pref = await get_preferences(user.id)
        if pref:
            saved_interests = [InterestCode(i) for i in (pref.get("interests") or [])]
            prefer_shorter_walks = pref.get("prefer_shorter_walks")

    data = await run_chat(
        req.message,
        req.context,
        trace,
        saved_interests,
        prefer_shorter_walks,
        req.history,
    )
    return Envelope.success(data=data, trace_id=trace.trace_id)
