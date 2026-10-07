"""즉시 추천(A) 요청/응답 계약.

신뢰 불변식(CLAUDE.md §6)을 스키마에 녹인다:
- 가격은 boolean(무료 여부)이 아니라 '상태값'. 빈값→free 매핑 불가.
- 모든 사실값에 provenance(confirmed/estimate/planned/unconfirmed).
- reasons 최대 2개, candidates 최대 4개(강제 채움 방지).
Phase 0 에서는 입력 검증을 느슨히 두고(스텁), A1 슬라이스에서 FR-A1~A4 로 강화한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class InterestCode(str, Enum):
    """사용자 관심사 6개 (PRD §6.4, A·B 공통 Soft Preference)."""

    TRADITIONAL = "traditional_culture"
    PALACES_HISTORIC = "palaces_historic"
    HANDS_ON = "hands_on"
    ART_EXHIBITIONS = "art_exhibitions"
    LIVE_PERFORMANCES = "live_performances"
    FESTIVALS_EVENTS = "festivals_events"


class ParsedConditions(BaseModel):
    """자연어 note에서 LLM이 구조화한 선택조건. '말한 것만' — 추정 금지(FR-A4)."""

    interests: list[InterestCode] = Field(
        default_factory=list,
        description="Cultural interests the user explicitly mentioned. Empty if none stated.",
    )
    avoid_interests: list[InterestCode] = Field(
        default_factory=list,
        description="Interests the user explicitly said they dislike / want to avoid. Empty if none stated.",
    )
    free_only: bool = Field(
        default=False,
        description="True ONLY if the user explicitly asked for free experiences only.",
    )
    budget_krw: int | None = Field(
        default=None,
        description="Max budget per experience in Korean won, if the user stated an amount. Null otherwise.",
    )
    indoor_outdoor: Literal["indoor", "outdoor"] | None = Field(
        default=None,
        description="Set only if the user explicitly preferred indoor or outdoor. Null otherwise.",
    )
    prefer_shorter_walks: bool = Field(
        default=False,
        description="True only if the user said they prefer shorter walks / less walking.",
    )


class ResultStatus(str, Enum):
    """사용자-facing 3상태 (FR-C3). '추천 제외'는 내부값이라 여기 없음."""

    FITS = "fits"
    CHECK_NEEDED = "check_needed"
    ALTERNATIVE = "alternative"


class ExperienceType(str, Enum):
    """D-06 유형 키 (DESIGN §3.4 icon-type-{key}). 모양 바뀌어도 키 고정."""

    HANDS_ON = "hands_on"
    PERFORMANCE = "performance"
    EXHIBITION = "exhibition"
    HISTORIC_VISIT = "historic_visit"
    FESTIVAL_EVENT = "festival_event"
    DEFAULT = "default"


class PriceStatus(str, Enum):
    """가격 정규화 (PRD §6.2). unknown/partial 을 free 로 바꾸지 않는다."""

    FREE = "free"
    PAID = "paid"
    UNKNOWN = "unknown"
    PARTIAL_OR_AMBIGUOUS = "partial_or_ambiguous"


class Provenance(str, Enum):
    """사실값 출처/신뢰 수준 (DESIGN §1·§5)."""

    CONFIRMED = "confirmed"  # 공식 확인값
    ESTIMATE = "estimate"  # ≈ 계산된 예상값
    PLANNED = "planned"  # 예정 (KONNECT 계획값)
    UNCONFIRMED = "unconfirmed"  # 미확인


class Reason(BaseModel):
    """추천 이유 (FR-C4). Reason Copy Dictionary v1.0 코드+문구만."""

    code: str  # 예: T01, I02, M03
    text: str


class TimeInfo(BaseModel):
    display: str
    provenance: Provenance


class PriceInfo(BaseModel):
    status: PriceStatus
    display: str  # 예: "Free", "유료·금액 미확인"
    raw: str | None = None  # 원본 문자열 보존(합성 금지)
    provenance: Provenance


class MovementInfo(BaseModel):
    walk_minutes: int | None = None
    distance_m: int | None = None
    display: str  # 예: "≈12 min walk", "Route unavailable"
    provenance: Provenance
    # 실제 도보 경로선 [[lat,lng],...]. 없으면 지도는 핀+외부지도로 폴백(임의 직선 금지).
    path: list[list[float]] | None = None


class UnconfirmedFlag(BaseModel):
    """미확인 flag 칩 (예: 'Price needs checking')."""

    text: str


class OfficialLink(BaseModel):
    label: str  # 예: "View official details"
    url: str


class Candidate(BaseModel):
    id: str
    title: str
    type: ExperienceType = ExperienceType.DEFAULT
    status: ResultStatus
    reasons: list[Reason] = Field(default_factory=list, max_length=2)
    time: TimeInfo | None = None
    price: PriceInfo | None = None
    movement: MovementInfo | None = None
    flags: list[UnconfirmedFlag] = Field(default_factory=list)
    image_url: str | None = None  # 공식 소스만. 없다고 제외하지 않는다.
    official_links: list[OfficialLink] = Field(default_factory=list)
    lat: float | None = None  # 지도 핀용 좌표
    lng: float | None = None


class StartLocation(BaseModel):
    """시작 위치 (FR-A1·A5). 좌표는 보유 시에만(없으면 라벨로 처리)."""

    label: str
    lat: float | None = None
    lng: float | None = None


class RecommendRequest(BaseModel):
    """FR-A1 필수 입력(+ FR-A4 자연어 선택조건).

    시작 위치·시작 시각·종료 시각이 필수. 현재 위치·현재 시각은 프론트에서
    '변경 가능한 기본값'으로 채워 보낸다(FR-A1·A6). 경계 검증은 domain/ 에서.
    """

    start_location: StartLocation
    start_at: datetime  # 시작 시각 (날짜 포함)
    end_at: datetime  # 종료 시각
    note: str | None = None  # 자연어 선택조건 1영역 (FR-A4). 구조화는 이후 LLM 단계.
    # 확인 시트에서 사용자가 이해한 조건을 확인/수정(✕ 제거)한 경우, 그 결과를
    # 넘겨 재파싱 대신 그대로 사용(사용자 교정 우선). None 이면 note 를 파싱한다.
    conditions: ParsedConditions | None = None


class ParseRequest(BaseModel):
    """확인 시트용 — note 를 '이해한 조건'으로만 구조화(추천 조회 없음)."""

    note: str | None = None


class RecommendData(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list, max_length=4)
    # 지도 출발점(해석된 좌표 포함). 지도 Start 핀·경로 기점.
    origin: StartLocation | None = None
    # AI가 note에서 이해한 조건(parsed chip 표시용 — '무엇을 이해했는지' 투명 공개).
    conditions: ParsedConditions | None = None
    # AI 관여 고지 (NFR-05, DESIGN §1): 프론트가 상단에 표시.
    ai_notice: str = "AI-assisted results · unconfirmed details marked"
