"""단일 챗봇 Agent 계약 (AG-1/2) — 자연어 → tool-calling → 통합 응답.

LLM 은 '어떤 tool 을 부를지'만 고르고, 사실(가격·시간·가용성)은 tool 내부 코드가 소유한다
(docs/agent-architecture.md §3 신뢰 경계). 응답의 사실값은 코드 fact 객체(RagAnswer·
RecommendData)에서 렌더 — LLM 산문이 사실을 다시 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.rag import RagAnswer
from app.models.recommend import RecommendData, StartLocation
from app.models.route import RouteData


class ChatKind(str, Enum):
    ANSWER = "answer"  # RAG 근거 답변
    RECOMMENDATION = "recommendation"  # 즉시 추천(개별 후보)
    ROUTE = "route"  # 하루 문화루트(2~3 스톱 코스)
    CLARIFY = "clarify"  # 되묻기(필수값 부족·의도 불명)


class ChatContext(BaseModel):
    """앱이 이미 가진 Trip 맥락(추천 tool 이 쓰는 필수 사실). LLM 이 만들지 않는다."""

    start_location: StartLocation | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class ChatTurn(BaseModel):
    """대화 히스토리 한 턴(멀티턴 맥락, AG-3). 사실 저장이 아니라 LLM 라우팅 맥락용."""

    role: Literal["user", "assistant"]
    content: str


class ChatHistory(BaseModel):
    """영속된 대화 복구 응답(L4) — 전체 누적 턴을 시간순으로."""

    turns: list[ChatTurn] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    context: ChatContext | None = None
    # 멀티턴 맥락 — 클라이언트가 이전 턴을 함께 보낸다(stateless 백엔드, 비로그인도 동작).
    history: list[ChatTurn] = Field(default_factory=list)


class ChatResponse(BaseModel):
    kind: ChatKind
    tool: str | None = None  # 실제로 호출된 tool 이름(투명·trace)
    message: str | None = None  # clarify 문구 또는 래퍼 텍스트
    answer: RagAnswer | None = None  # kind=answer
    recommendation: RecommendData | None = None  # kind=recommendation
    route: RouteData | None = None  # kind=route
    # 이 어시스턴트 턴의 라우팅 맥락 요약(멀티턴·영속 공용, L4). 사실 캐시가 아니라
    # "무엇을 제안했다"는 대화 맥락 텍스트 — 프론트 로컬 history·영속 저장이 같은 값을 쓴다.
    history_summary: str = ""
    # AI 관여 고지(NFR-05) — 프론트가 대화 상단에 표시.
    ai_notice: str = Field(
        default="AI-assisted · facts come from official sources, unconfirmed details marked"
    )


def summarize_response(data: ChatResponse) -> str:
    """어시스턴트 턴을 짧은 맥락 텍스트로 요약(멀티턴 맥락·영속 공용).

    LLM 이 후속 교정("make it shorter", "only free ones")을 이해하도록 '무엇을 제안했는지'
    만 남긴다. 사실값(가격·시간)을 재서술하지 않는다 — 사실은 코드 fact 객체가 소유.
    프론트 chat.js 의 summarize() 와 동일 규칙(정본은 여기, 프론트는 이 값을 사용).
    """
    parts: list[str] = []
    if data.route is not None:
        routes = data.route.routes or []
        if routes:
            r = routes[0]
            stops = " → ".join(s.candidate.title for s in r.stops)
            parts.append(f'Planned a route "{r.name}": {stops}')
        else:
            parts.append(data.route.unmet or "No route available.")
    if data.recommendation is not None:
        titles = [c.title for c in (data.recommendation.candidates or [])]
        parts.append(
            f"Suggested experiences: {', '.join(titles)}"
            if titles
            else "No experiences fit those conditions."
        )
    if data.answer is not None and data.answer.answer:
        parts.append(data.answer.answer)
    return "\n".join(parts) or (data.message or "")
