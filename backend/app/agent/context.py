"""Agent 컨텍스트 스키마 (CLAUDE §3·§4.1, FR-L5).

우선순위: Request > Trip > User Preference. 확인 가능한 사실·필수 조건은
개인화가 덮어쓰지 못한다. Phase 1(A1)에서는 RequestContext 만 구성하고,
Trip/Preference 는 Phase 2에서 더한다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, computed_field

from app.models.recommend import ParsedConditions, StartLocation


class RequestContext(BaseModel):
    """현재 요청 맥락 — 검증된 필수 입력 + 자연어 note(원문 보존)."""

    start_location: StartLocation
    start_at: datetime
    end_at: datetime
    note: str | None = None  # 자연어 선택조건 원문. 추정으로 채우지 않는다.
    # 확인 시트에서 사용자가 교정한 조건(있으면 재파싱 대신 사용 — 사용자 교정 우선).
    conditions: ParsedConditions | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available_minutes(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)
