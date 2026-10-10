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
import re
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
from app.domain.text_signals import detect_indoor_outdoor
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
    "Call exactly ONE recommendation tool per request — either plan_culture_route OR "
    "recommend_experiences, NEVER both — unless the user clearly asks for two separate things. "
    "When the user refines an earlier request ('make it shorter', 'only free ones', 'exclude "
    "museums', 'more traditional'), call the SAME tool as the previous turn and carry ALL "
    "still-relevant earlier conditions into the preferences plus the new one.\n"
    "Choosing the tool:\n"
    "- plan_culture_route is the DEFAULT. Use it whenever the user states interests, a place, "
    "or a vibe and wants something to do — build them a small multi-stop culture walk. This is "
    "what makes the chat different from the single-pick recommendation screen, so prefer it.\n"
    "- recommend_experiences: ONLY when the user explicitly asks for individual options or a "
    "single place instead of a route ('just recommend one place', 'a few spots to pick from', "
    "'one thing to see', 'suggest individual places').\n"
    "- answer_travel_question: a factual/FAQ question (transport, money, etiquette, what a "
    "cultural thing is). You may pair this with one recommendation tool only if the user asks a "
    "question AND wants ideas.\n"
    "When you have what you need, reply WITHOUT a tool. Write 2-3 natural, warm English "
    "sentences about THIS result: name the places you actually found and suggest a sensible "
    "order or how to enjoy them, and if you found fewer than the user asked for, say so plainly. "
    "Add a brief, genuine reason they'll like it. Do NOT state prices, opening hours, booking, "
    "or availability, and do not invent facts — the app renders all of those from official "
    "data; you only add friendly framing around the places named in the tool result.\n"
    "Location and time come from the app context, never from you. If the user only greets or "
    "there is no travel intent, reply without a tool and briefly ask what they'd like."
)

_SPATIAL_TOOLS = {RecommendExperiences.__name__, PlanCultureRoute.__name__}
# 챗봇 기본값 = route(추천A 단건과 구분). recommend 는 '개별/단건'을 명시했을 때만.
# 명시적 루트 신호(기본이 route라 보조적 — route 쪽 확정용).
_ROUTE_WORDS = (
    "route",
    "itinerary",
    "course",
    "plan ",
    "a plan",
    "tour",
    "take me around",
    "walk around",
    "whole day",
    "the day",
    "rest of",
)
# 명시적 '개별/단건 추천' 신호 → recommend. 이게 있어야 route 기본을 벗어난다.
_RECOMMEND_WORDS = (
    "recommend",
    "suggest",
    "one place",
    "a place",
    "one thing",
    "just one",
    "only one",
    "single",
    "a spot",
    "one spot",
    "individual",
    "an idea",
    "one idea",
    "few spots",
    "pick from",
    "options",
)


def _wants_route(message: str) -> bool:
    return any(w in message.lower() for w in _ROUTE_WORDS)


def _wants_recommend(message: str) -> bool:
    return any(w in message.lower() for w in _RECOMMEND_WORDS)


def _spatial_default(message: str) -> str:
    """한 턴에 둘 다 왔을 때 기본 선택(결정론). 우선순위: 명시적 루트어 > 명시적 개별추천어
    > 기본 route. 챗봇은 route 중심(추천A 단건 흐름과 구분)."""
    if _wants_route(message):
        return PlanCultureRoute.__name__
    if _wants_recommend(message):
        return RecommendExperiences.__name__
    return PlanCultureRoute.__name__


def _prior_spatial(history: list[ChatTurn] | None) -> str | None:
    """가장 최근 assistant 턴이 route/recommend 중 무엇을 냈는지 → 팔로업 연속성용.
    요약 마커로 판정(route 우선 — _present 의 kind 우선순위와 일치)."""
    for t in reversed(history or []):
        if t.role != "assistant":
            continue
        c = t.content.lower()
        if "planned a route" in c:
            return PlanCultureRoute.__name__
        if "suggested experiences" in c or "no experiences fit" in c:
            return RecommendExperiences.__name__
    return None


def _one_spatial(
    calls: list[dict], history: list[ChatTurn] | None, message: str, trace: Trace
) -> list[dict]:
    """과다호출 억제(Fix A): 한 턴에 recommend+route 가 동시에 오면 하나만 남긴다.

    선택 우선순위: (1) 직전 턴과 같은 tool(리파인 연속성), (2) 메시지의 명시적 루트 신호,
    (3) 기본 recommend. 비공간 tool(answer_travel_question)은 그대로 유지한다.
    """
    present = [c["name"] for c in calls if c["name"] in _SPATIAL_TOOLS]
    if len(present) <= 1:
        return calls
    keep = _prior_spatial(history)
    if keep not in present:
        kw = _spatial_default(message)
        keep = kw if kw in present else present[0]
    trace.step(
        "loop_single_intent",
        kept=keep,
        dropped=[n for n in present if n != keep],
    )
    result: list[dict] = []
    kept = False
    for c in calls:
        if c["name"] in _SPATIAL_TOOLS:
            if c["name"] == keep and not kept:
                result.append(c)
                kept = True
            # 나머지 공간 tool 은 실행에서 제외(아래에서 skip ToolMessage 로 계약만 충족)
        else:
            result.append(c)
    return result


@dataclass
class LoopState:
    """한 요청 동안 tool 결과(코드 사실)를 모은다. 사실 렌더는 여기서만(§6.4)."""

    context: ChatContext | None
    message: str = (
        ""  # 원본 사용자 메시지(위치 지명 감지용 — preferences 는 일부만 담음)
    )
    saved_interests: list[InterestCode] | None = None
    prefer_shorter_walks: bool | None = None
    saved_open_preferences: list[str] | None = None
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


_MAX_CONVO_TURNS = 12  # 조건 누적에 쓸 최근 user 발화 상한(토큰·안정)


def accumulated_user_text(history: list[ChatTurn] | None, message: str) -> str:
    """대화 전체의 user 발화를 모은다(최근 _MAX_CONVO_TURNS). 조건을 '사용자가 실제로 말한
    것'에서 누적 추출하기 위함 — LLM 의 매턴 요약이 이전 제외·위치를 흘려도 유실되지 않게."""
    turns = [t.content for t in (history or []) if t.role == "user"][-_MAX_CONVO_TURNS:]
    turns.append(message.strip())
    return "\n".join(t for t in turns if t and t.strip())


def latest_route_summary(history: list[ChatTurn] | None) -> str | None:
    """가장 최근 assistant 루트 요약에서 스톱 체인("A → B → C")만 추출(현재 루트 상태)."""
    for t in reversed(history or []):
        if t.role != "assistant" or "planned a route" not in t.content.lower():
            continue
        for line in t.content.splitlines():
            if "planned a route" in line.lower() and ":" in line:
                return line.split(":", 1)[1].strip()
    return None


def working_memory(history: list[ChatTurn] | None) -> str:
    """최근 대화의 '현재 루트'를 LLM 에 명시(P2) — 추가/삭제/변경을 현재 루트 기준으로 이해하고
    자연어 답변이 문맥을 유지하게. 실제 포함/제외는 코드(누적 conditions)가 결정론으로 강제."""
    route = latest_route_summary(history)
    if not route:
        return ""
    return (
        "[conversation so far] The culture route you have already given the user is: "
        f"{route}. If they ask to add to it, shorten it, swap, or remove a stop — or say they "
        "dislike or have already visited a place — you MUST call plan_culture_route AGAIN to "
        "rebuild it from live data. NEVER restate this route from memory without calling the "
        "tool. The tool automatically keeps the stops they still want, drops anything they "
        "rejected or already visited, and carries every earlier condition forward; the app "
        "renders the facts. In your final reply, refer naturally to the route and what changed."
    )


# 현재 턴이 '추가/복원' 의도임을 나타내는 마커 — 과거 제외를 뒤집는 신호(Request > Preference).
_ADDITIVE_MARKS = (
    "add",
    "include",
    "one more",
    "another",
    "also",
    "actually",
    "put back",
    "bring back",
    "i want",
    "i'd like",
    "show me",
    "back in",
)


_MORE_MARKS = ("more", "add", "another", "additional", "a few", "expand")
_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "another": 1,
    "couple": 2,
    "few": 3,
}


def _wants_more(message: str) -> bool:
    """현재 턴이 '더/추가' 요청인가 → 탐색 반경 목표 상향(문제1)."""
    return any(w in message.lower() for w in _MORE_MARKS)


def _parse_add_count(message: str) -> int:
    """'몇 개 더' 추가인지 파싱(digit > number word > 기본 1). 안전상 1~5 로 clamp."""
    m = message.lower()
    mt = re.search(r"\b(\d+)\b", m)
    if mt:
        return min(max(int(mt.group(1)), 1), 5)
    for w, n in _NUM_WORDS.items():
        if re.search(rf"\b{w}\b", m):
            return min(n, 5)
    return 1  # '더'라고만 함 → 1 개


def reconcile_reversals(cond: ParsedConditions, message: str) -> ParsedConditions:
    """번복 처리(§6 Request > Preference): 현재 메시지가 과거에 제외한 대상을 '추가/복원'해
    달라고 하면 그 대상을 제외에서 빼고(keywords 로 승격해 능동 검색). 예: 전에 "I don't like
    statue" 로 statue 가 exclude_concepts 에 있어도, 지금 "add one more statue" 면 해제한다.
    """
    m = message.lower()
    if not any(w in m for w in _ADDITIVE_MARKS):
        return cond

    def wanted(term: str) -> bool:
        core = term.lower().rstrip("s")
        return bool(core) and core in m

    kept_concepts = [c for c in cond.exclude_concepts if not wanted(c)]
    kept_places = [p for p in cond.exclude_places if not wanted(p)]
    restored = [c for c in cond.exclude_concepts if wanted(c)] + [
        p for p in cond.exclude_places if wanted(p)
    ]
    if not restored:
        return cond
    keywords = list(cond.keywords)
    for term in restored:
        if term not in keywords:
            keywords.append(term)  # 능동 검색으로 승격 — 해제만으로 안 나올 수 있으니
    return cond.model_copy(
        update={
            "exclude_concepts": kept_concepts,
            "exclude_places": kept_places,
            "keywords": keywords,
        }
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

    # [누적 조건] 전 대화의 user 발화를 모아 1회 파싱 → 제외·위치·선호의 '합집합'을 얻는다.
    # 라우팅 LLM 의 매턴 preferences 요약이 이전 제외를 흘려도, 사용자가 실제로 말한 조건을
    # 직접 누적하므로 제거한 장소가 다시 안 나오고 위치도 유지된다(route_orchestrator 가
    # exclude_places/concepts 를 하드 필터로 적용). 첫 턴은 현재 메시지만 → 기존과 동일.
    convo_text = accumulated_user_text(state.history, state.message)
    cond = await parse_note(convo_text) if convo_text.strip() else ParsedConditions()
    # [번복] 현재 턴이 과거 제외 대상을 '추가/복원'하면 제외 해제(Request 가 Preference 를 이김).
    before = (list(cond.exclude_concepts), list(cond.exclude_places))
    cond = reconcile_reversals(cond, state.message)
    if (cond.exclude_concepts, cond.exclude_places) != before:
        trace.step(
            "reversal",
            concepts=cond.exclude_concepts,
            places=cond.exclude_places,
            keywords=cond.keywords,
        )

    # [io 보강] 라우터 LLM 이 preferences 로 요약하며 'indoor/outdoor' 를 흘렸을 수 있다 →
    # 누적 발화에서 결정론으로 감지해 비어있을 때만 채운다(충돌 되묻기·실내외 랭킹 안정화).
    if cond.indoor_outdoor is None:
        io, strict = detect_indoor_outdoor(convo_text)
        if io:
            cond.indoor_outdoor = io
            cond.indoor_outdoor_strict = strict
            trace.step("io_backfill", pref=io, strict=strict)

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

    # [위치 우선·캐리포워드] 사용자가 대화 중 밝힌 지명을 앱 컨텍스트보다 우선(결정론 조회).
    # 누적 발화에서 감지 → 처음 말한 뒤 후속 턴('공원 빼줘' 등)에도 위치가 유지된다.
    loc = detect_location_in_text(convo_text) or context.start_location
    ctx = RequestContext(
        start_location=loc,
        start_at=context.start_at,
        end_at=context.end_at,
        note=(preferences or None),
        conditions=cond,
    )
    # [문제1] 사용자가 '더/추가'를 명시하면 탐색 목표를 올려 반경을 넓혀 후보를 발굴한다.
    want_more = _wants_more(state.message)
    if name == RecommendExperiences.__name__:
        from app.agent.orchestrator import recommend_a

        data = await recommend_a(
            ctx,
            trace,
            state.saved_interests,
            state.prefer_shorter_walks,
            state.saved_open_preferences,
            want_more=want_more,
        )
        state.recommendation = data
        titles = ", ".join(c.title for c in data.candidates) or "none"
        return f"Found {len(data.candidates)} experiences: {titles}."

    # [append] '더/추가' 요청이면 직전 루트 개수 + N 을 목표(max_stops)로 재생성 — 코드가
    # 개수를 정한다(LLM 아님, §6). 누적 제외 + 안정적 풀이라 보통 이전 스톱을 유지하며 늘어난다.
    prev = latest_route_summary(state.history)
    prev_count = len([t for t in prev.split("→") if t.strip()]) if prev else 0
    add_n = _parse_add_count(state.message) if want_more else 0
    target = prev_count + add_n if (add_n and prev_count) else None

    from app.agent.route_orchestrator import recommend_route

    route_data = await recommend_route(
        ctx,
        trace,
        state.saved_interests,
        state.prefer_shorter_walks,
        state.saved_open_preferences,
        want_more=want_more,
        max_stops=target,
    )
    state.route = route_data
    if not route_data.routes:
        return "No feasible route in the window."
    r0 = route_data.routes[0]
    stops = " → ".join(s.candidate.title for s in r0.stops)
    delivered = len(r0.stops)
    # [정직성·개수인지] 'N개 추가' 요청이면 실제 추가분을 세어, 못 채웠으면 그대로 알린다
    # (§6: 안 한 일을 했다고 하지 않음). 사실(가격·시간)은 전달 안 함.
    if target is not None:
        added = max(0, delivered - prev_count)
        if added < add_n:
            # 부족 사유 구분: 근처에 더 있는데 시간이 모자란 경우(more_feasible) vs 진짜 없음.
            if route_data.more_feasible:
                hint = (
                    "There ARE more cultural places nearby, but they don't fit the remaining "
                    "time as one walk. ASK the user if they'd like to extend their time window "
                    "to fit more stops."
                )
            else:
                hint = (
                    "No more feasible stops exist close enough — offer to widen the area or "
                    "adjust preferences."
                )
            return (
                f"Added only {added} of the {add_n} the user asked for. Route now has "
                f"{delivered} stops: {stops}. Tell the user honestly how many you could add; "
                f"do NOT claim you added more than this. {hint}"
            )
        return (
            f"Added {added} stop(s) as asked. Route now has {delivered} stops: {stops}."
        )
    return f"Built a {delivered}-stop walking route: {stops}."


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
    saved_open_preferences: list[str] | None = None,
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
        saved_open_preferences=saved_open_preferences,
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
    # [P2] 현재 루트를 명시한 working memory — 추가/삭제/변경을 현재 루트 기준으로.
    wm = working_memory(history)
    if wm:
        messages.append(SystemMessage(wm))
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
        # [Fix A] 과다호출 억제 — 한 턴에 공간추천(recommend/route)이 둘 다 오면 하나만 실행.
        run_calls = _one_spatial(calls, history, message.strip(), trace)
        # 실행은 run_calls 만. 같은 턴 tool 들은 병렬(멀티의도 지연↓) — asyncio 단일스레드라
        # 서로 다른 state 필드 기록은 안전. gather 는 순서 보존.
        observations = await asyncio.gather(
            *(
                _run_tool(call["name"], call.get("args") or {}, state, trace)
                for call in run_calls
            )
        )
        obs_by_id = {
            call.get("id", call["name"]): obs
            for call, obs in zip(run_calls, observations)
        }
        # 드롭된 tool_call 도 ToolMessage 를 붙여야 OpenAI 계약(모든 tool_call 응답)이 성립.
        # 드롭분은 실행하지 않고 skip 관측만 — 무거운 오케스트레이터를 돌리지 않는다.
        for call in calls:
            cid = call.get("id", call["name"])
            messages.append(
                ToolMessage(
                    obs_by_id.get(
                        cid,
                        "Skipped: only one recommendation tool runs per request; "
                        "use the other only if the user explicitly asks for both.",
                    ),
                    tool_call_id=cid,
                )
            )
        if state.clarify is not None:  # 필수사실/선호 미비 → 즉시 되묻기
            return state.clarify

    trace.step("agent_max_steps")
    return _present(state, None)
