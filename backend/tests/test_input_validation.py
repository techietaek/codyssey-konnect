"""가용시간 경계 검증 단위 테스트 (FR-A2·A3).

domain 결정론 로직을 조기에 테스트한다(agent-flow §1.4): 객관적 검증 신호.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ValidationFailure
from app.domain.input_validation import validate_available_time

BASE = datetime(2026, 10, 6, 15, 0)  # naive local


def test_valid_window_passes():
    # 정상: 3시간 10분
    validate_available_time(BASE, BASE + timedelta(hours=3, minutes=10))


def test_exactly_30_minutes_passes():
    # 경계 포함: 정확히 30분은 허용
    validate_available_time(BASE, BASE + timedelta(minutes=30))


def test_under_30_minutes_rejected():
    with pytest.raises(ValidationFailure, match="30 minutes"):
        validate_available_time(BASE, BASE + timedelta(minutes=29))


def test_end_equals_start_rejected():
    with pytest.raises(ValidationFailure, match="after start"):
        validate_available_time(BASE, BASE)


def test_end_before_start_rejected():
    with pytest.raises(ValidationFailure, match="after start"):
        validate_available_time(BASE, BASE - timedelta(minutes=10))


def test_end_up_to_midnight_passes():
    # 시작일 24:00(= 다음날 00:00)까지는 허용
    midnight = datetime(2026, 10, 7, 0, 0)
    validate_available_time(datetime(2026, 10, 6, 22, 0), midnight)


def test_end_past_midnight_rejected():
    # 자정 넘김(다음날 00:01)은 거부
    past = datetime(2026, 10, 7, 0, 1)
    with pytest.raises(ValidationFailure, match="midnight"):
        validate_available_time(datetime(2026, 10, 6, 22, 0), past)


def test_mixed_tzinfo_rejected():
    aware = BASE.replace(tzinfo=timezone.utc)
    with pytest.raises(ValidationFailure, match="same time format"):
        validate_available_time(BASE, aware + timedelta(hours=1))
