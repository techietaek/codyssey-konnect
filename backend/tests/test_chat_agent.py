"""챗봇 Agent dispatch — 결정론 분기 (LLM 라우팅은 제외, tool 실행 경로만).

LLM 선택(run_chat)은 비결정이라 단위테스트 대상이 아니다. '고른 tool 을 어떻게
실행·되묻기 하는가'(dispatch_tool)는 결정론이라 여기서 검증한다(사실 생성 금지·필수값 되묻기).
"""

import asyncio
from datetime import datetime

from app.agent import chat_agent
from app.agent.chat_agent import dispatch_tool, has_trip_context
from app.core.trace import Trace
from app.models.chat import ChatContext, ChatKind
from app.models.rag import RagAnswer
from app.models.recommend import StartLocation

_FULL_CTX = ChatContext(
    start_location=StartLocation(label="Insadong", lat=37.5717, lng=126.9858),
    start_at=datetime(2026, 10, 8, 10, 0),
    end_at=datetime(2026, 10, 8, 18, 0),
)


def test_has_trip_context_variants():
    assert has_trip_context(_FULL_CTX) is True
    assert has_trip_context(None) is False
    assert (
        has_trip_context(ChatContext(start_location=_FULL_CTX.start_location)) is False
    )
    # 위치만 없고 시간만 있어도 불완전 → False(추정 금지)
    assert (
        has_trip_context(
            ChatContext(start_at=_FULL_CTX.start_at, end_at=_FULL_CTX.end_at)
        )
        is False
    )


def test_answer_tool_routes_to_rag(monkeypatch):
    seen = {}

    async def fake_answer(q, trace):
        seen["q"] = q
        return RagAnswer(answer="grounded reply", grounded=True)

    monkeypatch.setattr(chat_agent, "answer_question", fake_answer)
    resp = asyncio.run(
        dispatch_tool("AnswerTravelQuestion", {"query": "tipping?"}, None, Trace())
    )
    assert resp.kind is ChatKind.ANSWER
    assert resp.answer.answer == "grounded reply"
    assert seen["q"] == "tipping?"


def test_recommend_tool_without_context_clarifies(monkeypatch):
    # 필수 사실(위치·시간) 없으면 추천 실행하지 않고 되묻는다(위치/시간 추정 금지).
    called = False

    async def fake_recommend(*a, **k):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "app.agent.orchestrator.recommend_a", fake_recommend, raising=False
    )
    resp = asyncio.run(
        dispatch_tool("RecommendExperiences", {"preferences": "art"}, None, Trace())
    )
    assert resp.kind is ChatKind.CLARIFY
    assert called is False  # recommend 호출 안 됨


def test_recommend_tool_with_context_runs(monkeypatch):
    captured = {}

    async def fake_recommend(ctx, trace, saved=None, walks=None):
        captured["note"] = ctx.note
        captured["label"] = ctx.start_location.label
        from app.models.recommend import RecommendData

        return RecommendData(candidates=[])

    monkeypatch.setattr("app.agent.orchestrator.recommend_a", fake_recommend)
    resp = asyncio.run(
        dispatch_tool(
            "RecommendExperiences", {"preferences": "love art"}, _FULL_CTX, Trace()
        )
    )
    assert resp.kind is ChatKind.RECOMMENDATION
    assert captured["note"] == "love art"  # 선호 표현은 note 로 전달
    assert captured["label"] == "Insadong"  # 위치는 context(사실)에서


def test_unknown_tool_clarifies():
    resp = asyncio.run(dispatch_tool("Nonsense", {}, _FULL_CTX, Trace()))
    assert resp.kind is ChatKind.CLARIFY
