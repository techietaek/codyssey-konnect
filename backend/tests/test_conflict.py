"""입력 충돌 감지(domain/conflict) 유닛테스트 — 순수 로직."""

from __future__ import annotations

from app.domain.conflict import conflict_message, io_interest_conflict
from app.models.recommend import InterestCode, ParsedConditions


def test_indoor_with_outdoor_interest_conflicts():
    cond = ParsedConditions(
        indoor_outdoor="indoor",
        interests=[InterestCode.PALACES_HISTORIC, InterestCode.ART_EXHIBITIONS],
    )
    out = io_interest_conflict(cond)
    assert InterestCode.PALACES_HISTORIC in out
    assert InterestCode.ART_EXHIBITIONS not in out  # 실내 관심사는 충돌 아님


def test_outdoor_with_indoor_interest_conflicts():
    cond = ParsedConditions(
        indoor_outdoor="outdoor", interests=[InterestCode.ART_EXHIBITIONS]
    )
    assert io_interest_conflict(cond) == [InterestCode.ART_EXHIBITIONS]


def test_no_conflict_when_aligned_or_no_pref():
    assert (
        io_interest_conflict(
            ParsedConditions(
                indoor_outdoor="outdoor", interests=[InterestCode.PALACES_HISTORIC]
            )
        )
        == []
    )
    assert (
        io_interest_conflict(
            ParsedConditions(interests=[InterestCode.PALACES_HISTORIC])
        )
        == []
    )


def test_neutral_interests_not_conflict():
    # traditional·live_performances 는 양쪽/중립 → 충돌로 보지 않는다.
    cond = ParsedConditions(
        indoor_outdoor="indoor",
        interests=[InterestCode.TRADITIONAL, InterestCode.LIVE_PERFORMANCES],
    )
    assert io_interest_conflict(cond) == []


def test_conflict_message_names_things_and_options():
    msg = conflict_message("indoor", [InterestCode.PALACES_HISTORIC])
    assert "indoor" in msg and "outdoor" in msg
    assert "palaces" in msg.lower()
    # 내부 enum 값이 그대로 노출되지 않는다.
    assert "palaces_historic" not in msg
