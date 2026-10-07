"""환경 정규화 — 공식 카테고리 등급 → Context (domain/environment). 결정론."""

from app.domain.environment import (
    air_grade_from_khai,
    build_environment,
    precipitation_from_pty,
)
from app.models.environment import AirGrade, Precipitation


def test_pty_mapping():
    assert precipitation_from_pty("0") is Precipitation.NONE
    assert precipitation_from_pty("1") is Precipitation.RAIN
    assert precipitation_from_pty("3") is Precipitation.SNOW
    assert precipitation_from_pty("2") is Precipitation.RAIN_SNOW
    assert precipitation_from_pty(None) is Precipitation.UNKNOWN
    assert precipitation_from_pty("9") is Precipitation.UNKNOWN  # 미상 코드


def test_khai_mapping():
    assert air_grade_from_khai("1") is AirGrade.GOOD
    assert air_grade_from_khai("4") is AirGrade.VERY_UNHEALTHY
    assert air_grade_from_khai(None) is AirGrade.UNKNOWN
    assert air_grade_from_khai("-") is AirGrade.UNKNOWN  # 측정소 결측


def test_adverse_on_rain():
    env = build_environment("1", "2")  # 비 + 대기 보통
    assert env.adverse is True
    assert env.precipitation is Precipitation.RAIN
    assert env.advisory and "rain" in env.advisory.lower()


def test_adverse_on_bad_air_without_rain():
    env = build_environment("0", "4")  # 강수 없음 + 대기 매우나쁨
    assert env.adverse is True
    assert env.advisory and "unhealthy" in env.advisory.lower()


def test_clear_moderate_not_adverse():
    env = build_environment("0", "2")  # 맑음 + 보통
    assert env.adverse is False
    assert env.advisory is None


def test_unknown_not_adverse():
    env = build_environment(None, None)  # 미확보 → unknown, adverse 아님
    assert env.adverse is False
    assert env.precipitation is Precipitation.UNKNOWN
    assert env.air_grade is AirGrade.UNKNOWN
    assert env.advisory is None
