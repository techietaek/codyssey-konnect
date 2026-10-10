"""Agentic while-loop 단위 테스트 (rollout 3). LLM·tool 실행은 모킹.

검증: 다단계 tool 호출 → 코드 결과 보관 → 구조화 ChatResponse 렌더(§6.4), 멀티의도,
필수사실 미비 clarify, max_steps·graceful. 실제 LLM/소스 호출 없음(결정론).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from langchain_core.messages import AIMessage

from app.agent import agent_loop as al
from app.agent import orchestrator as orch
from app.core.trace import Trace
from app.models.chat import ChatContext, ChatKind
from app.models.rag import RagAnswer
from app.models.recommend import Candidate, RecommendData, ResultStatus, StartLocation


class _FakeLLM:
    """scripted AIMessage 들을 순서대로 돌려주는 가짜 LLM(bind_tools no-op)."""

    def __init__(self, scripted):
        self.scripted = scripted
        self.i = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        msg = self.scripted[min(self.i, len(self.scripted) - 1)]
        self.i += 1
        return msg


def _patch_llm(monkeypatch, scripted):
    fake = _FakeLLM(scripted)
    monkeypatch.setattr(al, "ChatOpenAI", lambda **kw: fake)
    return fake


def _tool_call(name, args, cid="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid}])


def _final(text):
    return AIMessage(content=text)  # tool_calls 없음 → 루프 종료


def _ctx():
    return ChatContext(
        start_location=StartLocation(label="Gwanghwamun", lat=37.57, lng=126.98),
        start_at=datetime(2026, 10, 8, 13, 0),
        end_at=datetime(2026, 10, 8, 18, 0),
    )


def _recdata(*titles):
    return RecommendData(
        candidates=[
            Candidate(id=f"t-{i}", title=t, status=ResultStatus.FITS)
            for i, t in enumerate(titles)
        ]
    )


def _run(msg, context, history=None):
    return asyncio.run(al.run_chat_loop(msg, context, Trace(), history=history))


def test_faq_only(monkeypatch):
    _patch_llm(
        monkeypatch,
        [
            _tool_call("AnswerTravelQuestion", {"query": "subway?"}),
            _final("Here you go."),
        ],
    )

    async def fake_answer(q, trace):
        return RagAnswer(answer="Use a T-money card.", grounded=True)

    monkeypatch.setattr(al, "answer_knowledge", fake_answer)

    resp = _run("how do i take the subway?", _ctx())
    assert resp.kind is ChatKind.ANSWER
    assert resp.answer.answer == "Use a T-money card."
    assert resp.message == "Here you go."
    assert resp.tool == "AnswerTravelQuestion"


def test_recommend(monkeypatch):
    _patch_llm(
        monkeypatch,
        [
            _tool_call("RecommendExperiences", {"preferences": "traditional"}),
            _final("A few ideas near you."),
        ],
    )

    async def fake_rec(ctx, trace, saved=None, walks=None, open_prefs=None, **kw):
        return _recdata("Gyeongbokgung", "Bukchon")

    monkeypatch.setattr(orch, "recommend_a", fake_rec)

    resp = _run("what can I do?", _ctx())
    assert resp.kind is ChatKind.RECOMMENDATION
    assert [c.title for c in resp.recommendation.candidates] == [
        "Gyeongbokgung",
        "Bukchon",
    ]


def test_multi_intent_recommendation_wins_and_both_tools(monkeypatch):
    # 한 턴에 FAQ + 추천 두 tool → recommendation 우선 제시, 둘 다 tools_used.
    _patch_llm(
        monkeypatch,
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "AnswerTravelQuestion",
                        "args": {"query": "subway?"},
                        "id": "a",
                    },
                    {
                        "name": "RecommendExperiences",
                        "args": {"preferences": "indoor"},
                        "id": "b",
                    },
                ],
            ),
            _final("Here's info and some ideas."),
        ],
    )

    async def fake_answer(q, trace):
        return RagAnswer(answer="T-money.", grounded=True)

    async def fake_rec(ctx, trace, saved=None, walks=None, open_prefs=None, **kw):
        return _recdata("Leeum Museum")

    monkeypatch.setattr(al, "answer_knowledge", fake_answer)
    monkeypatch.setattr(orch, "recommend_a", fake_rec)

    resp = _run("subway? and what to do indoors?", _ctx())
    assert resp.kind is ChatKind.RECOMMENDATION  # primary = route > rec > answer
    assert "AnswerTravelQuestion" in resp.tool and "RecommendExperiences" in resp.tool
    # 멀티의도: 추천 AND 답을 모두 실어야 한다(한쪽을 버리지 않음).
    assert resp.recommendation is not None
    assert resp.answer is not None and resp.answer.answer == "T-money."


def test_missing_trip_context_clarifies(monkeypatch):
    _patch_llm(
        monkeypatch,
        [_tool_call("RecommendExperiences", {"preferences": "art"}), _final("...")],
    )
    # context 없음 → recommend_a 호출 전에 clarify 로 단락
    resp = _run("what can I do?", None)
    assert resp.kind is ChatKind.CLARIFY
    assert resp.message == al._CLARIFY_NEED_TRIP


def test_no_tool_greeting_clarifies(monkeypatch):
    _patch_llm(monkeypatch, [_final("Hi! What would you like to do in Seoul?")])
    resp = _run("hello", _ctx())
    assert resp.kind is ChatKind.CLARIFY
    assert resp.message == "Hi! What would you like to do in Seoul?"


def test_empty_message_clarifies():
    resp = _run("   ", _ctx())
    assert resp.kind is ChatKind.CLARIFY


def test_max_steps_graceful(monkeypatch):
    # LLM 이 계속 tool 만 부르면 상한 도달 → 지금까지 결과로 graceful 종료.
    _patch_llm(
        monkeypatch,
        [
            _tool_call("RecommendExperiences", {"preferences": "x"}, cid=f"c{i}")
            for i in range(10)
        ],
    )

    async def fake_rec(ctx, trace, saved=None, walks=None, open_prefs=None, **kw):
        return _recdata("Place")

    monkeypatch.setattr(orch, "recommend_a", fake_rec)
    resp = _run("ideas", _ctx())
    assert resp.kind is ChatKind.RECOMMENDATION  # best-so-far


def test_llm_failure_graceful(monkeypatch):
    class _BoomLLM:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            raise RuntimeError("network")

    monkeypatch.setattr(al, "ChatOpenAI", lambda **kw: _BoomLLM())
    resp = _run("ideas", _ctx())
    assert resp.kind is ChatKind.CLARIFY
    assert resp.message == al._FALLBACK
