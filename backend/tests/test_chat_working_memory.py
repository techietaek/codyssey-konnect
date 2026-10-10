"""멀티턴 working memory 헬퍼(결정론) — 누적 발화 수집·현재 루트 추출·recap 생성.
LLM 호출 없음. 조건 누적 자체(parse_note)는 라이브라 여기선 결정론 부분만 고정."""

from __future__ import annotations

from app.agent.agent_loop import (
    _parse_add_count,
    _wants_more,
    accumulated_user_text,
    latest_route_summary,
    reconcile_reversals,
    working_memory,
)
from app.models.chat import ChatTurn
from app.models.recommend import ParsedConditions


def _u(c):
    return ChatTurn(role="user", content=c)


def _a(c):
    return ChatTurn(role="assistant", content=c)


def test_accumulated_text_joins_user_turns_plus_current():
    history = [
        _u("I'm in Gwanghwamun, I love palaces"),
        _a('Planned a route "X": A → B'),
        _u("I don't like park"),
        _a('Planned a route "X": A → C'),
    ]
    text = accumulated_user_text(history, "been to Museum Kimchikan")
    # user 발화만, 시간순 + 현재 메시지. assistant 요약은 제외.
    assert "Gwanghwamun" in text and "don't like park" in text
    assert "been to Museum Kimchikan" in text
    assert "Planned a route" not in text


def test_accumulated_text_empty_history():
    assert accumulated_user_text(None, "hello") == "hello"


def test_latest_route_summary_extracts_stops():
    history = [
        _a('Planned a route "Old": A → B'),
        _u("remove B"),
        _a('Planned a route "New": A → C → D'),
    ]
    assert latest_route_summary(history) == "A → C → D"


def test_latest_route_summary_none_when_no_route():
    history = [_u("hi"), _a("Suggested experiences: A, B")]
    assert latest_route_summary(history) is None


def test_working_memory_names_current_route_and_forces_tool():
    history = [_a('Planned a route "X": Bosingak → Templestay Center')]
    wm = working_memory(history)
    assert "Bosingak → Templestay Center" in wm
    # 편집 시 반드시 tool 재호출(복창 금지) 지시가 포함돼야 함.
    assert "MUST call plan_culture_route" in wm


def test_working_memory_empty_without_route():
    assert working_memory([_u("hi")]) == ""


# ── 번복(Request > Preference): 과거 제외를 현재 '추가/복원' 요청이 뒤집는다 ──


def test_reversal_unexcludes_and_promotes_concept():
    cond = ParsedConditions(exclude_concepts=["statue"], exclude_places=["Templestay"])
    out = reconcile_reversals(cond, "please add one more statue")
    assert out.exclude_concepts == []  # statue 제외 해제
    assert "statue" in out.keywords  # 능동 검색으로 승격
    assert out.exclude_places == ["Templestay"]  # 언급 안 한 건 그대로 제외


def test_reversal_only_on_additive_intent():
    cond = ParsedConditions(exclude_concepts=["statue"])
    # '추가/복원' 신호 없음 → 그대로 제외 유지.
    assert reconcile_reversals(cond, "no statues please").exclude_concepts == ["statue"]


def test_reversal_no_match_keeps_exclusions():
    cond = ParsedConditions(exclude_concepts=["statue"])
    # additive 지만 대상이 일치하지 않음(개수만 추가) → 변경 없음.
    out = reconcile_reversals(cond, "can you add two more contents?")
    assert out.exclude_concepts == ["statue"]
    assert out.keywords == []


def test_parse_add_count():
    assert _parse_add_count("add two more") == 2
    assert _parse_add_count("add one more any content") == 1
    assert _parse_add_count("please add 3") == 3
    assert _parse_add_count("add a couple more") == 2
    assert _parse_add_count("add more") == 1  # 숫자 없음 → 1
    assert _parse_add_count("add 99") == 5  # 안전 clamp


def test_wants_more_detects_add_requests():
    assert _wants_more("can you add two more contents?")
    assert _wants_more("please add one more statue")
    assert _wants_more("show me a few more")
    assert not _wants_more("I don't like park")
    assert not _wants_more("make it shorter")


def test_reversal_place_restore():
    cond = ParsedConditions(exclude_places=["Templestay information center"])
    out = reconcile_reversals(cond, "actually add Templestay information center back")
    assert out.exclude_places == []
    assert "Templestay information center" in out.keywords
