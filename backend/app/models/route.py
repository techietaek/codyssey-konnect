"""B 문화루트 계약 (FR-B4~B8). A 후보(Candidate)·이동(MovementInfo) 재사용.

신뢰 불변식(CLAUDE §6):
- 체류시간을 근거 없이 지어내지 않는다(B-T01). 공식 소요시간 근거가 없으면 `예정` 분(minutes)을
  주장하지 않고, 방문시간은 사용자 계획 몫으로 둔다. 루트 total 은 **도보 이동시간**만(실근거).
- 필수 비용이 하나라도 미확인이면 루트 전체 `예산 충족` 금지 → `총비용 추가 확인 필요`.
- 2~3 스톱, 2·3개 동등, 3개 강제 채움 금지(walkable leg 상한으로 자연 결정).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.environment import EnvironmentContext
from app.models.recommend import (
    Candidate,
    MovementInfo,
    Provenance,
    ResultStatus,
    StartLocation,
    UnconfirmedFlag,
)


class RouteStop(BaseModel):
    order: int  # 1-based 방문 순서(시작점은 별도 origin)
    candidate: Candidate  # 장소 사실 전부 재사용(상태·가격·시간·flag·좌표·공식링크)
    # 계획 방문시간(B-T01): 공식 spendtime=confirmed / 유형 기준=planned. 도보 미확인 등으로
    # 절대 시각을 못 묶으면 arrival/depart=None(분·provenance 는 유지).
    visit_minutes: int | None = None
    visit_provenance: Provenance = Provenance.PLANNED
    arrival_at: datetime | None = None
    depart_at: datetime | None = None


class RouteSegment(BaseModel):
    """구간 이동(시작점→1, 1→2, …). 임의 직선 금지 — Tmap 실제값만, 실패는 unconfirmed."""

    from_label: str
    to_label: str
    movement: MovementInfo


class Route(BaseModel):
    id: str
    name: str  # FR-B8: 지역/주요장소 근거, 불가 시 "Culture route"
    headline: str = ""  # 코스 헤드라인 "N stops from {지역}"
    # 코스 전체 상태(요약) — 개별 스톱 배지를 덮지 않는다. fits=Ready / check=Still to check.
    status: ResultStatus = ResultStatus.FITS
    # 코스 전체 '가기 전 확인할 것' 집계("{내용} · {장소}").
    checks: list[str] = Field(default_factory=list)
    # 하루 동선: 개수 고정 제한 없음(Product) — 시간창이 길이를 정한다. max 는 안전 상한.
    stops: list[RouteStop] = Field(min_length=2, max_length=8)
    segments: list[RouteSegment] = Field(default_factory=list)
    # 루트 전체 도보 이동시간(알려진 구간 합, estimate). 한 구간이라도 미확인이면 None.
    total_walk_minutes: int | None = None
    walk_provenance: Provenance = Provenance.ESTIMATE
    budget_note: str  # 예: "Total cost needs checking" / "All stops free"
    stay_note: str  # 계획 방문시간 안내(예상/공식 구분)
    # 전체 종료 예상 시각(도보+방문 체인). 도보 미확인이면 None.
    finish_at: datetime | None = None
    flags: list[UnconfirmedFlag] = Field(default_factory=list)  # 루트 레벨 미확인


class RouteData(BaseModel):
    routes: list[Route] = Field(default_factory=list, max_length=3)
    origin: StartLocation | None = None
    # 신뢰 조합 부족/실패 사유(FR-B7) — 2개 미만이면 개별추천 전환 안내.
    unmet: str | None = None
    # 환경(날씨·대기질) Context — 악조건 시 주의 배너(PRD §6.6, Soft).
    environment: EnvironmentContext | None = None
    ai_notice: str = (
        "AI-assisted route · facts from official sources, unconfirmed details marked"
    )
