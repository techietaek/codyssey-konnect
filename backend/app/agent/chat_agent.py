"""단일 챗봇 Agent — tool-calling 라우팅 (AG-1/2).

[1] 자연어 입력 → [2] LLM 이 tool 선택(라우팅) → [3] 코드가 tool 실행 → [4] 통합 응답.
FAQ·여행정보·콘텐츠는 rag_search(answer_question), 추천은 recommend_a 로 분기한다.
B 문화루트는 이후 같은 패턴의 tool 로 추가(AG/B 단계).

신뢰 경계(docs/agent-architecture.md §3 — 2b 에서도 불변):
- LLM 은 '어떤 tool 을, 어떤 인자로'만 결정. 가격·시간·좌표·가용성·fits/check 는
  tool 내부 코드(domain/)·공식 데이터가 소유한다(LLM 이 사실을 만들지 않음).
- 필수 사실(위치·시간)이 없으면 추정하지 않고 되묻는다(clarify).
- 각 단계 trace(NFR-08).
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.agent.context import RequestContext
from app.agent.tools.schemas import (
    TOOL_SCHEMAS,
    AnswerTravelQuestion,
    PlanCultureRoute,
    RecommendExperiences,
)
from app.config import settings
from app.core.trace import Trace
from app.domain.input_validation import validate_available_time
from app.models.chat import ChatContext, ChatKind, ChatResponse, ChatTurn
from app.models.recommend import InterestCode
from app.rag.retrieve import answer_question

logger = logging.getLogger("konnect.agent")

_SYSTEM = (
    "You are KONNECT's assistant for foreign travelers in Seoul. For any travel intent you "
    "MUST call exactly one tool — never answer facts from your own knowledge.\n"
    "Pick the tool this way:\n"
    "1. plan_culture_route — the user wants a multi-stop plan, route, itinerary, or course, "
    "or asks what to do across a block of time (e.g. 'plan my afternoon', 'make me a route', "
    "'an itinerary', 'take me around', 'a culture walk').\n"
    "2. recommend_experiences — the user wants individual ideas for things to see or do now "
    "(e.g. 'what can I do', \"what's around\", 'suggest something', 'things to do near me', "
    "'any ideas', 'where should I go').\n"
    "3. answer_travel_question — a factual or FAQ question (transport, money, etiquette, "
    "connectivity, or what a cultural thing is).\n"
    "Always call a tool for any travel intent. Only reply WITHOUT a tool for a pure greeting "
    "or when there is genuinely no travel intent; then ask briefly what they'd like.\n"
    "You only route and extract the user's own wording; the tools own all facts (prices, "
    "hours, availability). This is a continuing conversation: when the user refines an earlier "
    "request ('exclude museums', 'make it shorter', 'only free ones', 'more traditional'), "
    "call the SAME tool again and carry ALL still-relevant earlier conditions into the "
    "preferences plus the new one. Location and time come from the app context."
)
_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        MessagesPlaceholder("history"),
        ("human", "{message}"),
    ]
)

_MAX_HISTORY = 10  # 최근 N 턴만 맥락으로(토큰 제어)


def to_lc_messages(history: list[ChatTurn]) -> list[BaseMessage]:
    """대화 히스토리 → LangChain 메시지(최근 _MAX_HISTORY 턴). 라우팅 맥락용."""
    msgs: list[BaseMessage] = []
    for turn in history[-_MAX_HISTORY:]:
        if turn.role == "user":
            msgs.append(HumanMessage(turn.content))
        else:
            msgs.append(AIMessage(turn.content))
    return msgs


_CLARIFY_DEFAULT = "What would you like to know or do in Seoul? I can answer travel questions or suggest experiences near you."
_CLARIFY_NEED_TRIP = (
    "Tell me where you're starting from and your available time, and I'll find cultural "
    "experiences you can actually do."
)
_FALLBACK = "Sorry, I couldn't process that just now. Could you rephrase?"


def has_trip_context(context: ChatContext | None) -> bool:
    """추천 tool 이 쓰는 필수 사실(위치·시작·종료)이 모두 있는지. 없으면 추정하지 않고 clarify."""
    return bool(
        context and context.start_location and context.start_at and context.end_at
    )


async def dispatch_tool(
    name: str,
    args: dict,
    context: ChatContext | None,
    trace: Trace,
    saved_interests: list[InterestCode] | None = None,
    prefer_shorter_walks: bool | None = None,
) -> ChatResponse:
    """LLM 이 고른 tool 을 코드로 실행 → 통합 응답. (라우팅과 분리되어 단독 테스트 가능)"""
    if name == AnswerTravelQuestion.__name__:
        ans = await answer_question(args.get("query") or "", trace)
        return ChatResponse(kind=ChatKind.ANSWER, tool=name, answer=ans)

    if name in (RecommendExperiences.__name__, PlanCultureRoute.__name__):
        # 추천·루트 모두 필수 사실(위치·시간)이 필요 — 없으면 추정 않고 되묻기.
        if not has_trip_context(context):
            trace.step("chat_clarify", reason="missing_trip_context", tool=name)
            return ChatResponse(
                kind=ChatKind.CLARIFY, tool=name, message=_CLARIFY_NEED_TRIP
            )
        # 사실(위치·시간)은 context 에서, 선호 표현만 LLM args 에서. 경계 검증은 domain.
        validate_available_time(context.start_at, context.end_at)
        ctx = RequestContext(
            start_location=context.start_location,
            start_at=context.start_at,
            end_at=context.end_at,
            note=(args.get("preferences") or None),
            conditions=None,
        )
        # 지연 import: 무거운 소스 체인을 끌어오므로 호출 시점에만.
        if name == RecommendExperiences.__name__:
            from app.agent.orchestrator import recommend_a

            data = await recommend_a(ctx, trace, saved_interests, prefer_shorter_walks)
            return ChatResponse(
                kind=ChatKind.RECOMMENDATION, tool=name, recommendation=data
            )
        from app.agent.route_orchestrator import recommend_route

        route_data = await recommend_route(
            ctx, trace, saved_interests, prefer_shorter_walks
        )
        return ChatResponse(kind=ChatKind.ROUTE, tool=name, route=route_data)

    # 알 수 없는 tool → 되묻기(사실 지어내지 않음).
    trace.step("chat_clarify", reason="unknown_tool", tool=name)
    return ChatResponse(kind=ChatKind.CLARIFY, message=_CLARIFY_DEFAULT)


async def run_chat(
    message: str,
    context: ChatContext | None,
    trace: Trace,
    saved_interests: list[InterestCode] | None = None,
    prefer_shorter_walks: bool | None = None,
    history: list[ChatTurn] | None = None,
) -> ChatResponse:
    if not message or not message.strip():
        return ChatResponse(kind=ChatKind.CLARIFY, message=_CLARIFY_DEFAULT)

    llm = ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        api_key=settings.openai_api_key,
        timeout=20,
    ).bind_tools(TOOL_SCHEMAS)
    try:
        ai = await (_PROMPT | llm).ainvoke(
            {"message": message.strip(), "history": to_lc_messages(history or [])}
        )
    except Exception as e:  # noqa: BLE001 — LLM/네트워크 실패는 되묻기로 graceful
        logger.warning("chat route failed: %s", type(e).__name__)
        trace.step("chat_route", error=type(e).__name__)
        return ChatResponse(kind=ChatKind.CLARIFY, message=_FALLBACK)

    calls = getattr(ai, "tool_calls", None) or []
    if not calls:
        # tool 미선택 = 잡담/불명확 → LLM 의 짧은 되묻기(사실 아님) 또는 기본 문구.
        trace.step("chat_route", tool=None)
        text = (ai.content if isinstance(ai.content, str) else "") or _CLARIFY_DEFAULT
        return ChatResponse(kind=ChatKind.CLARIFY, message=text)

    call = calls[0]  # 라우팅은 단일 tool(멀티소스 체이닝은 2b 이후)
    trace.step("chat_route", tool=call["name"])
    return await dispatch_tool(
        call["name"],
        call.get("args") or {},
        context,
        trace,
        saved_interests,
        prefer_shorter_walks,
    )
