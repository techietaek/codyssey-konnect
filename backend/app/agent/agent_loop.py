"""Agentic while-loop — 챗 전체(A 추천·B 루트·FAQ)를 하나의 다단계 tool-calling 루프로.

설계 docs/agent-architecture.md §6.1·§6.4. 루프: LLM 이 '어떤 tool 을 어떤 순서로'만
결정하고, 사실·판정·사실 렌더는 코드가 소유한다. 오케스트레이션은 경량 모델 허용
(settings.orchestrator_model, §6.7 — tool 선택만이라 신뢰경계 불변). 기본 off
(settings.agent_loop) — 기존 chat_agent 가 fallback.

신뢰 경계(불변):
- LLM 은 가격·운영시간·좌표·가용성을 생성하지 않는다. tool 이 공식 데이터·domain 으로 판정.
- 최종 사실 렌더는 LoopState 에 보관된 코드 결과(RecommendData/RouteData/RagAnswer)에서.
- 필수 사실(위치·시간)이 없으면 추정하지 않고 clarify. 루프 상한·graceful·매 턴 trace.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from app.agent.chat_agent import (
    _ASK_PREFS,
    _CLARIFY_DEFAULT,
    _CLARIFY_NEED_TRIP,
    _FALLBACK,
    _asked_prefs,
    has_trip_context,
    to_lc_messages,
)
from app.agent.context import RequestContext
from app.agent.note_parser import parse_note
from app.agent.tools.knowledge import answer_knowledge
from app.agent.tools.schemas import (
    AnswerTravelQuestion,
    PlanCultureRoute,
    RecommendExperiences,
)
from app.config import settings
from app.core.exceptions import ValidationFailure
from app.core.trace import Trace
from app.domain.conflict import conflict_message, io_interest_conflict
from app.domain.input_validation import validate_available_time
from app.domain.locations import detect_location_in_text
from app.models.chat import ChatContext, ChatKind, ChatResponse, ChatTurn
from app.models.rag import RagAnswer
from app.models.recommend import InterestCode, ParsedConditions, RecommendData
from app.models.route import RouteData

logger = logging.getLogger("konnect.agent")

# 이전 어시스턴트 턴이 실내/외 충돌을 물었는지 판정하는 마커(재질문 방지).
_IO_CONFLICT_MARKS = ("are mostly outdoor", "are mostly indoor")


def _asked_io_conflict(history: list[ChatTurn] | None) -> bool:
    """직전까지 실내/외 충돌 되묻기를 이미 했으면 True(답을 받은 뒤 또 묻지 않음)."""
    return any(
        t.role == "assistant"
        and any(m in t.content.lower() for m in _IO_CONFLICT_MARKS)
        for t in (history or [])
    )


_MAX_STEPS = 6  # 무한루프·비용 방어
_LOOP_TOOLS = [AnswerTravelQuestion, RecommendExperiences, PlanCultureRoute]

_SYSTEM = (
    "You are KONNECT's assistant for foreign travelers in Seoul. Help them find cultural "
    "experiences they can actually do now, plan a day route, or answer travel questions.\n"
    "Use tools — never answer travel facts (prices, hours, availability, what's nearby) from "
    "your own knowledge. The tools own all facts; you only decide which tools to call and pass "
    "the user's own wording.\n"
    "You may call tools across several turns: e.g. answer a question AND find experiences if the "
    "user asked for both. When you have everything needed, reply WITHOUT a tool — a short, "
    "friendly English message introducing the results (do not restate prices/hours; the app "
    "renders those).\n"
    "Tools:\n"
    "- answer_travel_question: a factual/FAQ question (transport, money, etiquette, what a "
    "cultural thing is).\n"
    "- recommend_experiences: the user wants individual ideas for things to see or do now.\n"
    "- plan_culture_route: the user wants a multi-stop day route / itinerary / course.\n"
    "Carry forward still-relevant earlier conditions when the user refines a request. Location "
    "and time come from the app context, never from you. If the user only greets or there is no "
    "travel intent, reply without a tool and briefly ask what they'd like."
)


@dataclass
class LoopState:
    """한 요청 동안 tool 결과(코드 사실)를 모은다. 사실 렌더는 여기서만(§6.4)."""

    context: ChatContext | None
    message: str = (
        ""  # 원본 사용자 메시지(위치 지명 감지용 — preferences 는 일부만 담음)
    )
    saved_interests: list[InterestCode] | None = None
    prefer_shorter_walks: bool | None = None
    history: list[ChatTurn] | None = None
    recommendation: RecommendData | None = None
    route: RouteData | None = None
    answer: RagAnswer | None = None
    tools_used: list[str] = field(default_factory=list)
    clarify: ChatResponse | None = None  # 필수사실/선호 미비 → 즉시 되묻기(추정 금지)


def _ctx_summary(context: ChatContext | None) -> str:
    """LLM 에 '앱 컨텍스트 가용 여부'만 알린다(값=사실은 tool 이 소유, 여기서 노출 최소)."""
    if has_trip_context(context):
        return (
            "\n\n[app context: the user's start location and time window are available, so "
            "recommend_experiences / plan_culture_route can run.]"
        )
    return (
        "\n\n[app context: no start location or time window yet — if the user wants "
        "recommendations or a route, ask them for it instead of guessing.]"
    )


async def _run_recommend_or_route(
    name: str, preferences: str, state: LoopState, trace: Trace
) -> str:
    """추천/루트 tool 실행(필수사실·선호 선체크 → recommend_a/route). 관측 문자열 반환.

    위치·시간 미비, 또는 추천에 선호 미지정+미질문이면 clarify 로 단락(사실 지어내지 않음).
    """
    context = state.context
    if not has_trip_context(context):
        trace.step("loop_clarify", reason="missing_trip_context", tool=name)
        state.clarify = ChatResponse(
            kind=ChatKind.CLARIFY, tool=name, message=_CLARIFY_NEED_TRIP
        )
        return "Cannot run: the user has not provided a start location and time window."

    if (
        name == RecommendExperiences.__name__
        and not preferences
        and not _asked_prefs(state.history)
    ):
        trace.step("loop_clarify", reason="no_preferences", tool=name)
        state.clarify = ChatResponse(
            kind=ChatKind.CLARIFY, tool=name, message=_ASK_PREFS
        )
        return (
            "Need preferences first: ask the user what kind of experiences they want."
        )

    # 시간 경계 위반(예: 30분 미만)은 사용자-facing 메시지를 그대로 되묻는다 —
    # 루프의 generic tool-error 핸들러가 삼켜 모호한 문구로 바뀌지 않게 여기서 잡는다.
    try:
        validate_available_time(context.start_at, context.end_at)
    except ValidationFailure as e:
        trace.step("loop_clarify", reason="invalid_time", tool=name)
        state.clarify = ChatResponse(
            kind=ChatKind.CLARIFY, tool=name, message=e.user_message
        )
        return f"Invalid time window: {e.user_message}"

    # 조건을 여기서 한 번만 구조화(아래 recommend 에 conditions 로 넘겨 재파싱 방지).
    cond = await parse_note(preferences) if preferences else ParsedConditions()

    # [충돌 되묻기] 실내/외 선호 ↔ 관심사 모순(예: indoor + 궁궐)이면 조용히 한쪽을 버리지
    # 않고 되묻는다(Request 우선 — 사용자 프롬프트가 최우선). 이미 물었으면 그대로 진행.
    conflicting = io_interest_conflict(cond)
    if conflicting and not _asked_io_conflict(state.history):
        trace.step("loop_clarify", reason="io_interest_conflict", tool=name)
        state.clarify = ChatResponse(
            kind=ChatKind.CLARIFY,
            tool=name,
            message=conflict_message(cond.indoor_outdoor or "", conflicting),
        )
        return (
            "Conflicting request (indoor/outdoor vs interests); ask the user to choose."
        )

    # [위치 우선] 사용자가 프롬프트에 직접 밝힌 지명을 앱 컨텍스트보다 우선(결정론 조회).
    # 원본 메시지에서 감지(preferences 는 선호만 담아 "I am at Myeongdong"을 누락할 수 있음).
    loc = detect_location_in_text(state.message) or context.start_location
    ctx = RequestContext(
        start_location=loc,
        start_at=context.start_at,
        end_at=context.end_at,
        note=(preferences or None),
        conditions=cond,
    )
    if name == RecommendExperiences.__name__:
        from app.agent.orchestrator import recommend_a

        data = await recommend_a(
            ctx, trace, state.saved_interests, state.prefer_shorter_walks
        )
        state.recommendation = data
        titles = ", ".join(c.title for c in data.candidates) or "none"
        return f"Found {len(data.candidates)} experiences: {titles}."

    from app.agent.route_orchestrator import recommend_route

    route_data = await recommend_route(
        ctx, trace, state.saved_interests, state.prefer_shorter_walks
    )
    state.route = route_data
    n = len(route_data.routes)
    return (
        f"Built {n} day route option(s)." if n else "No feasible route in the window."
    )


async def _run_tool(name: str, args: dict, state: LoopState, trace: Trace) -> str:
    """tool 하나 실행 → LLM 에 돌려줄 관측 요약(사실 전문 아님). 결과 객체는 state 에 보관."""
    if name not in state.tools_used:
        state.tools_used.append(name)
    try:
        if name == AnswerTravelQuestion.__name__:
            ans = await answer_knowledge(args.get("query") or "", trace)
            state.answer = ans
            return f"Knowledge answer ready (grounded={ans.grounded})."
        if name in (RecommendExperiences.__name__, PlanCultureRoute.__name__):
            return await _run_recommend_or_route(
                name, (args.get("preferences") or "").strip(), state, trace
            )
    except Exception as e:  # noqa: BLE001 — 한 tool 실패가 루프를 막지 않게 graceful
        logger.warning("loop tool %s failed: %s", name, type(e).__name__)
        trace.step("loop_tool_error", tool=name, error=type(e).__name__)
        return f"Tool {name} failed; proceed with what you have."
    return f"Unknown tool {name}."


def _present(state: LoopState, final_ai: AIMessage | None) -> ChatResponse:
    """LoopState 의 코드 결과 → 구조화 ChatResponse. 사실은 코드 결과에서 렌더(§6.4).

    여러 의도가 섞이면 route > recommendation > answer 우선 1종으로 제시(3단계 단순화),
    LLM 의 자연어 텍스트는 message 로 함께 전달. 아무 결과도 없으면 clarify.
    """
    text = ""
    if final_ai is not None and isinstance(final_ai.content, str):
        text = final_ai.content.strip()
    tool = ",".join(state.tools_used) or None

    # 멀티의도: 모은 결과(추천+루트+FAQ답)를 모두 싣는다 — 하나만 담아 나머지를 버리지 않는다.
    # kind 는 primary 힌트(route>recommendation>answer), 프론트는 실린 필드를 모두 렌더.
    if state.route is None and state.recommendation is None and state.answer is None:
        return ChatResponse(
            kind=ChatKind.CLARIFY, tool=tool, message=text or _CLARIFY_DEFAULT
        )
    if state.route is not None:
        kind = ChatKind.ROUTE
    elif state.recommendation is not None:
        kind = ChatKind.RECOMMENDATION
    else:
        kind = ChatKind.ANSWER
    return ChatResponse(
        kind=kind,
        tool=tool,
        message=text or None,
        recommendation=state.recommendation,
        route=state.route,
        answer=state.answer,
    )


async def run_chat_loop(
    message: str,
    context: ChatContext | None,
    trace: Trace,
    saved_interests: list[InterestCode] | None = None,
    prefer_shorter_walks: bool | None = None,
    history: list[ChatTurn] | None = None,
) -> ChatResponse:
    """§6.1 while-loop: LLM tool 선택 → 코드 실행 → 결과 재투입 → 더 쓸 tool 없으면 종료."""
    if not message or not message.strip():
        return ChatResponse(kind=ChatKind.CLARIFY, message=_CLARIFY_DEFAULT)

    state = LoopState(
        context=context,
        message=message.strip(),
        saved_interests=saved_interests,
        prefer_shorter_walks=prefer_shorter_walks,
        history=history,
    )
    # 오케스트레이션(tool 선택)은 경량 모델 허용(§6.7, settings.orchestrator_model) — 지연↓.
    # tool 선택만 담당하고 사실·판정은 코드(tool)가 소유하므로 신뢰경계는 불변.
    llm = ChatOpenAI(
        model=settings.agent_orchestrator_model,
        temperature=0,
        api_key=settings.openai_api_key,
        timeout=30,
    ).bind_tools(_LOOP_TOOLS)

    messages: list[BaseMessage] = [SystemMessage(_SYSTEM)]
    messages += to_lc_messages(history or [])
    messages.append(HumanMessage(message.strip() + _ctx_summary(context)))

    for step in range(_MAX_STEPS):
        try:
            ai = await llm.ainvoke(messages)
        except Exception as e:  # noqa: BLE001 — LLM/네트워크 실패 → graceful
            logger.warning("loop llm failed: %s", type(e).__name__)
            trace.step("agent_turn", turn=step, error=type(e).__name__)
            # 이미 모은 결과가 있으면 그걸로 종료, 없으면 되묻기.
            return (
                _present(state, None)
                if state.tools_used
                else ChatResponse(kind=ChatKind.CLARIFY, message=_FALLBACK)
            )

        calls = getattr(ai, "tool_calls", None) or []
        trace.step("agent_turn", turn=step, tools=[c["name"] for c in calls])
        if not calls:
            return _present(state, ai)

        messages.append(ai)
        # 같은 턴의 tool 들은 병렬 실행(멀티의도 지연↓). asyncio 단일스레드라 서로 다른
        # state 필드 기록은 안전. gather 는 순서 보존 → ToolMessage 를 tool_call 순서대로 붙인다.
        observations = await asyncio.gather(
            *(
                _run_tool(call["name"], call.get("args") or {}, state, trace)
                for call in calls
            )
        )
        for call, obs in zip(calls, observations):
            messages.append(ToolMessage(obs, tool_call_id=call.get("id", call["name"])))
        if state.clarify is not None:  # 필수사실/선호 미비 → 즉시 되묻기
            return state.clarify

    trace.step("agent_max_steps")
    return _present(state, None)
