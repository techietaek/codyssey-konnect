"""표시 순서(Soft 랭킹) — A안: 등급 우선 + 같은 등급 내 관심사 선호/비선호 (PRD §5.3).

신뢰 경계:
- Soft Preference 는 **우선순위만 조정**한다. 비선호여도 후보를 Hard 제외하지 않는다
  (개인화가 사실/가용성을 덮지 않음 — CLAUDE §6.6, FR-L5).
- 1차 키는 결과 상태(fits→alternative→check_needed). 관심사는 **같은 등급 안에서만**
  순서를 바꾸고, 그다음은 거리순(호출부가 거리순 리스트를 안정 정렬로 넘긴다).
- 본격 Soft 스코어링(저장된 Preference·Trip 반영, 후보 선발 영향)은 Phase 2/3(B안).
  이 모듈은 그 토대다.
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


def preference_rank(cand: Candidate, cond: ParsedConditions) -> int:
    """0=선호 매칭, 1=중립, 2=비선호 매칭. 같은 등급 내 Soft 순서용(제외 아님).
    선호와 비선호가 동시에 걸리면 선호 우선(강등하지 않음)."""
    types = TYPE_INTERESTS.get(cand.type, set())
    if any(i in types for i in cond.interests):
        return 0
    if any(i in types for i in cond.avoid_interests):
        return 2
    return 1


def display_sort_key(cand: Candidate, cond: ParsedConditions) -> tuple[int, int]:
    """(상태등급, 관심사순위). 안정 정렬이면 같은 키 안에서 거리순이 유지된다."""
    return (_STATUS_RANK.get(cand.status, 99), preference_rank(cand, cond))
