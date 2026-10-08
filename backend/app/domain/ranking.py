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

# 야외 노출형(휴리스틱, 사실 아님) — 악천후·실내외 선호 Soft 강등용. 전시·체험은 대개
# 실내. 공식 Outdoor 태그가 없어 유형으로 근사하며 **제외·사실표기엔 쓰지 않는다**(Soft only).
OUTDOOR_EXPOSED_TYPES = {
    ExperienceType.HISTORIC_VISIT,
    ExperienceType.FESTIVAL_EVENT,
}
INDOOR_TYPES = {
    ExperienceType.EXHIBITION,
    ExperienceType.HANDS_ON,
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


def io_rank(etype: ExperienceType, cond: ParsedConditions) -> int:
    """실내외 선호 순위 0=일치 / 1=중립(또는 선호 없음) / 2=불일치. Soft(제외 아님).
    공식 태그가 없어 유형 휴리스틱으로 근사 — 그래서 Hard 제외하지 않고 강등만 한다."""
    pref = cond.indoor_outdoor
    if pref == "outdoor":
        if etype in OUTDOOR_EXPOSED_TYPES:
            return 0
        if etype in INDOOR_TYPES:
            return 2
    elif pref == "indoor":
        if etype in INDOOR_TYPES:
            return 0
        if etype in OUTDOOR_EXPOSED_TYPES:
            return 2
    return 1


def weather_rank(cand: Candidate, adverse: bool) -> int:
    """악천후 시 야외 노출형을 1(뒤로), 그 외 0. Soft only — 제외 아님(PRD §6.6).
    관심사 다음 2차 키라 '원하는 콘텐츠'는 계속 앞에 두고 실내를 소폭 우선한다."""
    return 1 if adverse and cand.type in OUTDOOR_EXPOSED_TYPES else 0


def io_rank_with_verdict(
    cand: Candidate, cond: ParsedConditions, verdict: str | None
) -> int:
    """실내외 Soft 순위 — LLM per-place 분류(verdict) 우선, 없으면 유형 휴리스틱 fallback.
    verdict 'unknown'/없음+선호없음은 중립(1). 유형추측보다 정확(탑골공원 등 오분류 해소)."""
    pref = cond.indoor_outdoor
    if pref is None:
        return 1
    if verdict in ("indoor", "outdoor"):
        return 0 if verdict == pref else 2
    if verdict == "unknown":
        return 1  # 분류 불가 → 중립(강등 안 함)
    return io_rank(cand.type, cond)  # 분류 없음 → 유형 휴리스틱


def display_sort_key(
    cand: Candidate,
    cond: ParsedConditions,
    adverse: bool = False,
    io_verdicts: dict[str, str] | None = None,
) -> tuple[int, int, int, int]:
    """(관심사, 실내외 선호, 날씨, 상태등급). 명시 선호(관심사·실내외)가 먼저 →
    악천후면 실내 소폭 우선 → 상태등급. 안정 정렬이면 같은 키 안에서 거리순 유지.
    io_verdicts(LLM 분류 {id:setting})가 있으면 유형추측 대신 그것으로 실내외 순위."""
    return (
        preference_rank(cand, cond),
        io_rank_with_verdict(cand, cond, (io_verdicts or {}).get(cand.id)),
        weather_rank(cand, adverse),
        _STATUS_RANK.get(cand.status, 99),
    )
