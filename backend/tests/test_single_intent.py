"""Fix A — 과다호출 억제(_one_spatial) 결정론 가드. LLM 이 한 턴에 recommend+route 를
둘 다 호출해도 코드가 하나로 좁히는지(비공간 tool 은 유지) 검증. LLM 호출 없음."""

from __future__ import annotations

from app.agent.agent_loop import (
    _one_spatial,
    _prior_spatial,
    _spatial_default,
    _wants_recommend,
    _wants_route,
)
from app.agent.tools.schemas import (
    AnswerTravelQuestion,
    PlanCultureRoute,
    RecommendExperiences,
)
from app.core.trace import Trace
from app.models.chat import ChatTurn

REC = RecommendExperiences.__name__
ROUTE = PlanCultureRoute.__name__
ASK = AnswerTravelQuestion.__name__


def _call(name: str, cid: str | None = None) -> dict:
    return {"name": name, "args": {}, "id": cid or name}


def _names(calls: list[dict]) -> list[str]:
    return [c["name"] for c in calls]


def test_single_call_passes_through():
    calls = [_call(REC)]
    assert _one_spatial(calls, None, "what can I do", Trace()) == calls


def test_both_collapse_to_route_by_default():
    out = _one_spatial(
        [_call(REC), _call(ROUTE)], None, "palaces, I love to walk", Trace()
    )
    # 챗봇 기본 = route(추천A와 구분) → route 유지, recommend 드롭.
    assert _names(out) == [ROUTE]


def test_both_collapse_to_route_on_explicit_route_word():
    out = _one_spatial(
        [_call(REC), _call(ROUTE)], None, "plan me a route for today", Trace()
    )
    assert _names(out) == [ROUTE]


def test_both_collapse_to_recommend_on_explicit_single():
    out = _one_spatial(
        [_call(REC), _call(ROUTE)], None, "just recommend one place to see", Trace()
    )
    assert _names(out) == [REC]


def test_followup_keeps_prior_route():
    history = [
        ChatTurn(role="user", content="plan my afternoon"),
        ChatTurn(role="assistant", content='Planned a route "X": A → B'),
    ]
    # 리파인("make it shorter")에 둘 다 와도 직전 route 로 연속.
    out = _one_spatial([_call(REC), _call(ROUTE)], history, "make it shorter", Trace())
    assert _names(out) == [ROUTE]


def test_followup_keeps_prior_recommend():
    history = [
        ChatTurn(role="user", content="what can I do"),
        ChatTurn(role="assistant", content="Suggested experiences: A, B"),
    ]
    out = _one_spatial([_call(REC), _call(ROUTE)], history, "only free ones", Trace())
    assert _names(out) == [REC]


def test_non_spatial_tool_preserved():
    # answer + 둘 다 → answer 유지 + 공간 하나.
    out = _one_spatial(
        [_call(ASK), _call(REC), _call(ROUTE)], None, "do I tip, and ideas?", Trace()
    )
    assert ASK in _names(out)
    assert len([n for n in _names(out) if n in (REC, ROUTE)]) == 1


def test_duplicate_same_tool_deduped():
    out = _one_spatial([_call(REC, "a"), _call(REC, "b")], None, "ideas", Trace())
    assert _names(out) == [REC]


def test_wants_route_excludes_walk_preference():
    assert not _wants_route("I love to walk")  # 선호어는 route 아님
    assert _wants_route("make me a route")
    assert _wants_route("plan my afternoon")


def test_spatial_default_is_route():
    # 기본 route(추천A와 구분). 개별/단건 명시일 때만 recommend. 루트어가 있으면 route 우선.
    assert _spatial_default("I like palaces and quiet places") == ROUTE
    assert _spatial_default("recommend one place") == REC
    assert _wants_recommend("just one spot to pick from")
    assert _spatial_default("suggest a route") == ROUTE  # 루트어가 recommend어보다 우선


def test_prior_spatial_route_wins_when_both_in_summary():
    history = [
        ChatTurn(
            role="assistant",
            content='Planned a route "X": A → B\nSuggested experiences: C, D',
        )
    ]
    assert _prior_spatial(history) == ROUTE
