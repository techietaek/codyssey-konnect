"""가용시간 경계 검증 (FR-A2·A3).

추천 '전에' 입력 오류·제한을 걸러낸다. 이는 시스템 예외(FR-C7)도,
정상 0건 결과도 아니다 → ValidationFailure(422)로 분리한다.

경계 규칙(PRD §4.2 FR-A2):
- 최소 가용시간 30분 이상
- 종료 경계는 '시작일 24:00'까지 (= 시작일 다음 자정). 자정 넘김 금지.
- 시작 ≥ 종료면 종료 재선택 요청
- 종료 자동 기본값/자동 연장은 프론트에서 금지(백엔드는 받은 값만 검증)
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from app.core.exceptions import ValidationFailure

MIN_AVAILABLE = timedelta(minutes=30)


def _start_day_boundary(start_at: datetime) -> datetime:
    """시작일 24:00 = 시작일 다음 날 00:00."""
    next_day = (start_at + timedelta(days=1)).date()
    return datetime.combine(next_day, time.min, tzinfo=start_at.tzinfo)


def validate_available_time(start_at: datetime, end_at: datetime) -> None:
    """가용시간 경계 검증. 위반 시 ValidationFailure(사용자-facing 메시지).

    tz 혼용(한쪽만 aware)은 비교 불가 → 입력 오류로 처리한다.
    """
    if (start_at.tzinfo is None) != (end_at.tzinfo is None):
        raise ValidationFailure("Start and end time must use the same time format.")

    if end_at <= start_at:
        raise ValidationFailure("End time must be after start time.")

    if end_at - start_at < MIN_AVAILABLE:
        raise ValidationFailure("Please allow at least 30 minutes.")

    if end_at > _start_day_boundary(start_at):
        raise ValidationFailure("End time must be by midnight of the start day.")
