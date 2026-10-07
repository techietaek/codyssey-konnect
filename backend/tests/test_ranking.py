"""표시 순서(Soft 랭킹) 테스트 — 등급 우선 + 같은 등급 내 선호/비선호 (A안).

핵심: Soft 는 순서만. 비선호여도 제외하지 않는다(개인화가 가용성을 덮지 않음).
"""

from __future__ import annotations

from app.domain.normalize import type_from_contenttype
from app.domain.ranking import (
    display_sort_key,
    preference_rank,
    type_preference_rank,
    weather_rank,
)
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


def test_preference_outranks_status_b_plan():
    # B안(관심사 우선): 원하는 유형이면 check_needed 라도 중립 fits 보다 먼저.
    # (사실은 안 바뀜 — 각 카드의 상태 배지는 그대로 fits/check 로 표기)
    cond = ParsedConditions(interests=[InterestCode.LIVE_PERFORMANCES])
    liked_check = _cand(ExperienceType.PERFORMANCE, ResultStatus.CHECK_NEEDED)
    neutral_fit = _cand(ExperienceType.HISTORIC_VISIT, ResultStatus.FITS)
    assert display_sort_key(liked_check, cond) < display_sort_key(neutral_fit, cond)


def test_status_breaks_tie_within_same_interest():
    # 같은 관심사 안에서는 상태가 2차 키 — fits 가 check 앞.
    cond = ParsedConditions(interests=[InterestCode.ART_EXHIBITIONS])
    liked_fit = _cand(ExperienceType.EXHIBITION, ResultStatus.FITS)
    liked_check = _cand(ExperienceType.EXHIBITION, ResultStatus.CHECK_NEEDED)
    assert display_sort_key(liked_fit, cond) < display_sort_key(liked_check, cond)


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


def test_weather_rank_demotes_outdoor_only_when_adverse():
    outdoor = _cand(ExperienceType.HISTORIC_VISIT)
    indoor = _cand(ExperienceType.EXHIBITION)
    assert weather_rank(outdoor, adverse=True) == 1  # 악천후 → 야외 뒤로
    assert weather_rank(indoor, adverse=True) == 0  # 실내 영향 없음
    assert weather_rank(outdoor, adverse=False) == 0  # 평상시 영향 없음(불이익 금지)


def test_interest_stays_primary_over_weather():
    # 악천후여도 '원하는 콘텐츠'(관심사)가 먼저 — 날씨는 2차(FR-B4 유지).
    cond = ParsedConditions(interests=[InterestCode.PALACES_HISTORIC])  # 야외 선호
    liked_outdoor = _cand(ExperienceType.HISTORIC_VISIT)
    neutral_indoor = _cand(ExperienceType.EXHIBITION)
    assert display_sort_key(liked_outdoor, cond, adverse=True) < display_sort_key(
        neutral_indoor, cond, adverse=True
    )


def test_weather_breaks_tie_within_same_interest():
    # 관심사 동률(중립)에서 악천후면 실내 소폭 우선.
    cond = ParsedConditions()
    outdoor = _cand(ExperienceType.HISTORIC_VISIT)
    indoor = _cand(ExperienceType.EXHIBITION)
    assert display_sort_key(indoor, cond, adverse=True) < display_sort_key(
        outdoor, cond, adverse=True
    )


def test_type_preference_rank_for_selection():
    # 선발(조회 풀 재정렬)용 — 유형만으로 0/1/2. contenttypeid → 유형 매핑과 결합.
    cond = ParsedConditions(interests=[InterestCode.ART_EXHIBITIONS])
    assert type_preference_rank(type_from_contenttype("78"), cond) == 0  # 미술관=선호
    assert type_preference_rank(type_from_contenttype("76"), cond) == 1  # 역사=중립
    assert type_preference_rank(type_from_contenttype(None), cond) == 1  # 미상=중립
