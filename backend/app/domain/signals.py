"""AI 분류 근거 키워드 (표시 전용, 신뢰 투명 UX).

추천 카드·루트 스톱의 'AI 로고' 토글이 보여줄 **분류 신호 키워드**를 만든다. 핵심 원칙:
파이프라인이 **이미 산정한** 분류(유형·실내외·관심사·가격)를 그대로 영문 키워드로 노출한다
— 새 사실을 생성하지 않는다(§6). 개발자는 "코드/LLM 분류가 의도대로 됐나"를, 사용자는
"이 콘텐츠가 어떻게 구분되나"를 확인한다.

각 신호엔 matched 플래그가 붙는다 — 그 분류가 **사용자가 명시한 조건**(관심사·실내외·무료)과
일치하면 True(UI 녹색), 아니면 기본 분류(흰색). 매칭 판정도 cond 기반 결정론 — 생성 아님.

신뢰 경계:
- 여기서 만드는 키워드는 **표시 전용** — Hard 판정·랭킹에 되먹이지 않는다.
- 실내외는 LLM per-place 분류(verdict) 우선, 없으면 유형 휴리스틱(ranking 과 동일 신호).
- 가격/유형은 공식 데이터 기반 정규화 결과를 라벨로만 옮긴다.
"""

from __future__ import annotations

from app.domain.ranking import (
    INDOOR_TYPES,
    OUTDOOR_EXPOSED_TYPES,
    TYPE_INTERESTS,
)
from app.models.recommend import (
    Candidate,
    ClassificationSignal,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    PriceStatus,
)

# 유형(코드 분류) → 영문 키워드. default 는 키워드 없음(억지 라벨 금지).
_TYPE_KEYWORD: dict[ExperienceType, str] = {
    ExperienceType.HISTORIC_VISIT: "historic site",
    ExperienceType.EXHIBITION: "exhibition",
    ExperienceType.PERFORMANCE: "performance",
    ExperienceType.HANDS_ON: "hands-on",
    ExperienceType.FESTIVAL_EVENT: "festival",
}

# 관심사(콘텐츠가 충족하는 카테고리) → 영문 키워드. 유형 키워드와 중복은 dedup 으로 제거.
_INTEREST_KEYWORD: dict[InterestCode, str] = {
    InterestCode.TRADITIONAL: "traditional",
    InterestCode.PALACES_HISTORIC: "palace & historic",
    InterestCode.HANDS_ON: "hands-on",
    InterestCode.ART_EXHIBITIONS: "art",
    InterestCode.LIVE_PERFORMANCES: "performance",
    InterestCode.FESTIVALS_EVENTS: "festival",
}

_MAX_SIGNALS = 5


def classification_signals(
    cand: Candidate,
    cond: ParsedConditions | None = None,
    io_verdict: str | None = None,
) -> list[ClassificationSignal]:
    """후보의 분류 신호(영문, 순서 보존 dedup). 표시 전용 — 사실 생성 아님.

    순서: 유형 → 관심사 카테고리 → 실내/외 → 가격. io_verdict(LLM 실내외 분류)가 있으면
    유형 휴리스틱보다 우선한다. 각 신호의 matched 는 사용자 명시 조건(cond)과 일치 여부.
    알 수 없으면 해당 신호는 생략(없는 분류를 지어내지 않음).
    """
    cond = cond or ParsedConditions()
    interests = set(cond.interests)
    pairs: list[tuple[str, bool]] = []  # (label, matched)

    type_kw = _TYPE_KEYWORD.get(cand.type)
    if type_kw:
        # 유형은 그 유형이 충족하는 관심사 중 하나라도 사용자가 요청했으면 매칭.
        type_matched = bool(TYPE_INTERESTS.get(cand.type, set()) & interests)
        pairs.append((type_kw, type_matched))

    for ic in TYPE_INTERESTS.get(cand.type, set()):
        kw = _INTEREST_KEYWORD.get(ic)
        if kw:
            pairs.append((kw, ic in interests))

    # 실내/외: LLM 분류 verdict 우선, 없으면 유형 휴리스틱(ranking 과 동일 신호), 둘 다 없으면 생략.
    io = io_verdict if io_verdict in ("indoor", "outdoor") else None
    if io is None:
        if cand.type in INDOOR_TYPES:
            io = "indoor"
        elif cand.type in OUTDOOR_EXPOSED_TYPES:
            io = "outdoor"
    if io is not None:
        pairs.append((io, cond.indoor_outdoor == io))

    if cand.price is not None:
        if cand.price.status is PriceStatus.FREE:
            pairs.append(("free", cond.free_only))
        elif cand.price.status is PriceStatus.PAID:
            pairs.append(("paid", False))  # 유료는 사용자 요청 매칭 대상 아님

    # 순서 보존 dedup(대소문자 무시) — 같은 라벨은 matched OR 로 합친다.
    order: list[str] = []
    matched_by: dict[str, bool] = {}
    for label, matched in pairs:
        key = label.lower()
        if key not in matched_by:
            order.append(label)
            matched_by[key] = matched
        else:
            matched_by[key] = matched_by[key] or matched
    return [
        ClassificationSignal(label=label, matched=matched_by[label.lower()])
        for label in order
    ][:_MAX_SIGNALS]
