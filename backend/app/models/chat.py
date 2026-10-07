"""단일 챗봇 Agent 계약 (AG-1/2) — 자연어 → tool-calling → 통합 응답.

LLM 은 '어떤 tool 을 부를지'만 고르고, 사실(가격·시간·가용성)은 tool 내부 코드가 소유한다
(docs/agent-architecture.md §3 신뢰 경계). 응답의 사실값은 코드 fact 객체(RagAnswer·
RecommendData)에서 렌더 — LLM 산문이 사실을 다시 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

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


class ChatRequest(BaseModel):
    message: str
    context: ChatContext | None = None


class ChatResponse(BaseModel):
    kind: ChatKind
    tool: str | None = None  # 실제로 호출된 tool 이름(투명·trace)
    message: str | None = None  # clarify 문구 또는 래퍼 텍스트
    answer: RagAnswer | None = None  # kind=answer
    recommendation: RecommendData | None = None  # kind=recommendation
    route: RouteData | None = None  # kind=route
    # AI 관여 고지(NFR-05) — 프론트가 대화 상단에 표시.
    ai_notice: str = Field(
        default="AI-assisted · facts come from official sources, unconfirmed details marked"
    )
