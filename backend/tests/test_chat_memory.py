"""summarize_response (L4 Long-term memory) — 어시스턴트 턴 맥락 요약.

영속 저장·멀티턴 맥락이 쓰는 요약 텍스트가 종류별로 올바른지(사실 재서술 없이 '무엇을
제안했는지'만). 프론트 chat.js summarize() 와 동일 규칙.
"""

from __future__ import annotations

from app.models.chat import ChatKind, ChatResponse, summarize_response
from app.models.rag import RagAnswer
from app.models.recommend import Candidate, RecommendData, ResultStatus
from app.models.route import Route, RouteData, RouteStop


def _cand(title: str) -> Candidate:
    return Candidate(id=title, title=title, status=ResultStatus.FITS)


def test_summary_recommendation_lists_titles():
    data = ChatResponse(
        kind=ChatKind.RECOMMENDATION,
        recommendation=RecommendData(candidates=[_cand("Gyeongbokgung"), _cand("Bukchon")]),
    )
    assert summarize_response(data) == "Suggested experiences: Gyeongbokgung, Bukchon"


def test_summary_recommendation_empty_is_honest():
    data = ChatResponse(
        kind=ChatKind.RECOMMENDATION, recommendation=RecommendData(candidates=[])
    )
    assert summarize_response(data) == "No experiences fit those conditions."


def test_summary_route_names_stops():
    route = Route(
        id="r1",
        name="Insadong walk",
        stops=[
            RouteStop(order=1, candidate=_cand("Jogyesa")),
            RouteStop(order=2, candidate=_cand("Insadong-gil")),
        ],
        budget_note="All stops free",
        stay_note="",
    )
    data = ChatResponse(kind=ChatKind.ROUTE, route=RouteData(routes=[route]))
    assert summarize_response(data) == 'Planned a route "Insadong walk": Jogyesa → Insadong-gil'


def test_summary_route_unmet_when_no_routes():
    data = ChatResponse(
        kind=ChatKind.ROUTE, route=RouteData(routes=[], unmet="Not enough time.")
    )
    assert summarize_response(data) == "Not enough time."


def test_summary_answer_uses_answer_text():
    data = ChatResponse(
        kind=ChatKind.ANSWER, answer=RagAnswer(answer="Tipping isn't expected.", grounded=True)
    )
    assert summarize_response(data) == "Tipping isn't expected."


def test_summary_clarify_falls_back_to_message():
    data = ChatResponse(kind=ChatKind.CLARIFY, message="What would you like to do?")
    assert summarize_response(data) == "What would you like to do?"
