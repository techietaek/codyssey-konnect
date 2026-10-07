"""표시 순서(Soft 랭킹) — B안: 관심사 우선 → 상태등급 → 거리 (PRD §5.3, FR-B4).

Product 결정(2026-10-07): 관심사가 **선발까지** 영향 + **관심사 우선**(거리는 2차).
"무작정 가까운 것"이 아니라 "원하는 콘텐츠 중 가까운 것을 자연스럽게".

신뢰 경계(결정과 무관하게 유지 — CLAUDE §6):
- Soft Preference 는 **순서/우선순위만** 조정한다. 비선호여도 Hard 제외하지 않는다
  (명시 배제만 제거 — domain/exclusion). 개인화가 사실/가용성을 덮지 않는다(FR-L5).
- 표시 키 = (관심사순위, 상태등급). 거리는 호출부가 '관심사→거리'로 정렬해 넘긴 리스트를
  **안정 정렬**해 관심사·상태 같은 구간 안에서 거리순으로 보존된다.
- 선발(후보 구성) 영향은 orchestrator 가 조회 풀을 관심사 우선으로 재정렬해 반영한다.
"""

from __future__ import annotations

from app.models.recommend import (
    Candidate,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    ResultStatus,
)

# 후보 유형이 충족하는 관심사(내부 5유형↔6관심사, 1:1 아님). reasons 도 이 맵을 쓴다.
TYPE_INTERESTS: dict[ExperienceType, set[InterestCode]] = {
    ExperienceType.HISTORIC_VISIT: {
        InterestCode.PALACES_HISTORIC,
        InterestCode.TRADITIONAL,
    },
    ExperienceType.EXHIBITION: {InterestCode.ART_EXHIBITIONS},
    ExperienceType.PERFORMANCE: {InterestCode.LIVE_PERFORMANCES},
    ExperienceType.FESTIVAL_EVENT: {InterestCode.FESTIVALS_EVENTS},
    ExperienceType.HANDS_ON: {InterestCode.HANDS_ON, InterestCode.TRADITIONAL},
    ExperienceType.DEFAULT: set(),
}

# 표시 순서 우선도: 조건 충족 > 완화 대안 > 추가 확인 필요.
_STATUS_RANK = {
    ResultStatus.FITS: 0,
    ResultStatus.ALTERNATIVE: 1,
    ResultStatus.CHECK_NEEDED: 2,
}


def type_preference_rank(etype: ExperienceType, cond: ParsedConditions) -> int:
    """유형 기준 0=선호 / 1=중립 / 2=비선호. 선호·비선호 동시 매칭이면 선호 우선.
    조회 풀 재정렬(선발)·표시 순서 공용 — 유형만 알면 되므로 상세조회 전에도 쓸 수 있다."""
    types = TYPE_INTERESTS.get(etype, set())
    if any(i in types for i in cond.interests):
        return 0
    if any(i in types for i in cond.avoid_interests):
        return 2
    return 1


def preference_rank(cand: Candidate, cond: ParsedConditions) -> int:
    """후보의 관심사 순위(0/1/2). type_preference_rank 를 후보 유형에 적용."""
    return type_preference_rank(cand.type, cond)


def display_sort_key(cand: Candidate, cond: ParsedConditions) -> tuple[int, int]:
    """(관심사순위, 상태등급). 관심사 우선(B안). 안정 정렬이면 같은 키 안에서 거리순 유지."""
    return (preference_rank(cand, cond), _STATUS_RANK.get(cand.status, 99))
