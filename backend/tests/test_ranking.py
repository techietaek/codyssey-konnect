"""표시 순서(Soft 랭킹) 테스트 — 등급 우선 + 같은 등급 내 선호/비선호 (A안).

핵심: Soft 는 순서만. 비선호여도 제외하지 않는다(개인화가 가용성을 덮지 않음).
"""

from __future__ import annotations

from app.domain.ranking import display_sort_key, preference_rank
from app.models.recommend import (
    Candidate,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    ResultStatus,
)


def _cand(etype, status=ResultStatus.FITS, title="x"):
    return Candidate(
        id=title,
        title=title,
        type=etype,
        status=status,
        reasons=[],
        flags=[],
        official_links=[],
    )


def test_preference_rank_liked_neutral_avoided():
    cond = ParsedConditions(
        interests=[InterestCode.ART_EXHIBITIONS],
        avoid_interests=[InterestCode.LIVE_PERFORMANCES],
    )
    liked = _cand(ExperienceType.EXHIBITION)
    avoided = _cand(ExperienceType.PERFORMANCE)
    neutral = _cand(ExperienceType.HISTORIC_VISIT)
    assert preference_rank(liked, cond) == 0
    assert preference_rank(neutral, cond) == 1
    assert preference_rank(avoided, cond) == 2


def test_liked_beats_avoided_when_both_match():
    # 한 유형이 선호·비선호 둘 다에 걸리면 선호 우선(강등 안 함)
    cond = ParsedConditions(
        interests=[InterestCode.TRADITIONAL],
        avoid_interests=[InterestCode.PALACES_HISTORIC],
    )
    c = _cand(ExperienceType.HISTORIC_VISIT)  # {palaces_historic, traditional}
    assert preference_rank(c, cond) == 0


def test_status_outranks_preference():
    # 등급이 1차 키 — 선호해도 check_needed 가 fits 앞에 오지 않는다
    cond = ParsedConditions(interests=[InterestCode.LIVE_PERFORMANCES])
    liked_check = _cand(ExperienceType.PERFORMANCE, ResultStatus.CHECK_NEEDED)
    neutral_fit = _cand(ExperienceType.HISTORIC_VISIT, ResultStatus.FITS)
    assert display_sort_key(neutral_fit, cond) < display_sort_key(liked_check, cond)


def test_sort_stable_keeps_distance_within_grade():
    cond = ParsedConditions(avoid_interests=[InterestCode.FESTIVALS_EVENTS])
    # 거리순으로 들어온 같은 등급 리스트: 비선호는 뒤로, 나머지는 원순서 유지
    near_avoid = _cand(ExperienceType.FESTIVAL_EVENT, title="near_avoid")
    mid = _cand(ExperienceType.EXHIBITION, title="mid")
    far = _cand(ExperienceType.HISTORIC_VISIT, title="far")
    ordered = [near_avoid, mid, far]  # 거리순
    ordered.sort(key=lambda c: display_sort_key(c, cond))
    assert [c.title for c in ordered] == ["mid", "far", "near_avoid"]


def test_avoided_not_excluded():
    # 랭킹은 제외하지 않는다 — 비선호도 리스트에 남는다(강등만)
    cond = ParsedConditions(avoid_interests=[InterestCode.LIVE_PERFORMANCES])
    only = _cand(ExperienceType.PERFORMANCE)
    assert preference_rank(only, cond) == 2  # 존재하되 뒤로
