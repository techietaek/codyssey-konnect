"""agentic 루프의 충돌 되묻기 + 프롬프트 위치 우선 통합테스트. LLM·parse·recommend 모킹.

검증: (1) indoor↔궁궐 충돌이면 recommend 호출 없이 CLARIFY, (2) 프롬프트의 지명이 앱
컨텍스트 위치를 덮어써 recommend_a 에 전달된다. 실제 LLM/소스 호출 없음(결정론).
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from langchain_core.messages import AIMessage

from app.agent import agent_loop as al
from app.agent import orchestrator as orch
from app.core.trace import Trace
from app.models.chat import ChatContext, ChatKind
from app.models.recommend import (
    Candidate,
    InterestCode,
    ParsedConditions,
    RecommendData,
    ResultStatus,
    StartLocation,
)


class _FakeLLM:
    def __init__(self, scripted):
        self.scripted, self.i = scripted, 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        msg = self.scripted[min(self.i, len(self.scripted) - 1)]
        self.i += 1
        return msg


def _patch_llm(monkeypatch, scripted):
    monkeypatch.setattr(al, "ChatOpenAI", lambda **kw: _FakeLLM(scripted))


def _call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c1"}])


def _ctx(label="Current location", lat=37.5700, lng=126.9830):
    return ChatContext(
        start_location=StartLocation(label=label, lat=lat, lng=lng),
        start_at=datetime(2026, 10, 15, 13, 0),
        end_at=datetime(2026, 10, 15, 18, 0),
    )


def test_io_interest_conflict_short_circuits_to_clarify(monkeypatch):
    _patch_llm(
        monkeypatch,
        [
            _call("PlanCultureRoute", {"preferences": "indoor, palaces"}),
            AIMessage(content="x"),
        ],
    )

    async def fake_parse(note):
        return ParsedConditions(
            indoor_outdoor="indoor", interests=[InterestCode.PALACES_HISTORIC]
        )

    monkeypatch.setattr(al, "parse_note", fake_parse)

    r = asyncio.run(
        al.run_chat_loop("indoor route but I love palaces", _ctx(), Trace())
    )
    assert r.kind == ChatKind.CLARIFY
    assert "mostly outdoor" in (r.message or "")
    assert r.route is None  # 충돌 → 루트 생성 안 함


def test_short_window_surfaces_validation_message(monkeypatch):
    # 30분 미만 창 → generic tool-error 로 삼켜지지 말고 사용자-facing 사유를 되묻는다.
    _patch_llm(
        monkeypatch,
        [_call("PlanCultureRoute", {"preferences": "palaces"}), AIMessage(content="x")],
    )
    ctx = ChatContext(
        start_location=StartLocation(label="Myeongdong", lat=37.5637, lng=126.985),
        start_at=datetime(2026, 10, 15, 17, 40),
        end_at=datetime(2026, 10, 15, 18, 0),  # 20분 < 30분 최소
    )
    r = asyncio.run(al.run_chat_loop("plan a walk", ctx, Trace()))
    assert r.kind == ChatKind.CLARIFY
    assert "30 minutes" in (r.message or "")


def test_prompt_location_overrides_app_context(monkeypatch):
    _patch_llm(
        monkeypatch,
        [
            _call("RecommendExperiences", {"preferences": "art museums"}),
            AIMessage(content="here"),
        ],
    )

    async def fake_parse(note):
        return ParsedConditions()  # 충돌 없음

    monkeypatch.setattr(al, "parse_note", fake_parse)

    captured = {}

    async def fake_recommend_a(ctx, trace, saved=None, walks=None):
        captured["loc"] = ctx.start_location
        return RecommendData(
            candidates=[Candidate(id="t1", title="A", status=ResultStatus.FITS)]
        )

    monkeypatch.setattr(orch, "recommend_a", fake_recommend_a)

    # 앱 컨텍스트는 default(종각) 좌표지만 메시지에 Myeongdong 이 있으면 그쪽을 쓴다.
    r = asyncio.run(
        al.run_chat_loop("suggest art museums, I am at Myeongdong", _ctx(), Trace())
    )
    assert r.kind == ChatKind.RECOMMENDATION
    assert abs(captured["loc"].lat - 37.5637) < 0.01  # Myeongdong
    assert captured["loc"].lng != 126.9830  # 종각 default 가 아님
