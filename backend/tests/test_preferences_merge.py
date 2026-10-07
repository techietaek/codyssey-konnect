"""저장 선호 병합 테스트 (Phase 2 L2 · FR-L4·L5).

핵심 불변식: Request(note) 우선 — 저장 선호는 note 침묵 시에만 관심사를 Soft 채움,
이번 요청 기피 관심사는 저장 선호로도 넣지 않는다. 원본 불변.
"""

from __future__ import annotations

from app.domain.preferences_merge import merge_saved_interests
from app.models.recommend import InterestCode, ParsedConditions

ART = InterestCode.ART_EXHIBITIONS
TRAD = InterestCode.TRADITIONAL
PALACE = InterestCode.PALACES_HISTORIC


def test_note_interests_win_over_saved():
    """note 가 관심사를 말했으면 저장 선호는 적용하지 않는다(과개인화 방지)."""
    cond = ParsedConditions(interests=[ART])
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == [ART]


def test_saved_fills_when_note_silent():
    """note 가 관심사를 말하지 않으면 저장 관심사를 Soft 신호로 채운다."""
    cond = ParsedConditions()
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == [TRAD, PALACE]


def test_avoided_this_request_not_refilled():
    """이번 요청에서 기피한 관심사는 저장 선호로도 다시 넣지 않는다."""
    cond = ParsedConditions(avoid_interests=[TRAD])
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == [PALACE]


def test_no_saved_is_noop():
    cond = ParsedConditions()
    assert merge_saved_interests(cond, None).interests == []
    assert merge_saved_interests(cond, []).interests == []


def test_all_saved_avoided_leaves_empty():
    """저장 관심사가 전부 이번 기피면 채우지 않는다(빈 상태 유지)."""
    cond = ParsedConditions(avoid_interests=[TRAD, PALACE])
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == []


def test_original_not_mutated():
    cond = ParsedConditions()
    merge_saved_interests(cond, [TRAD])
    assert cond.interests == []  # 원본 불변
