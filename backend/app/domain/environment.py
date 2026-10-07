"""환경 정규화 — 공식 카테고리 등급 → Context (PRD §6.6). 결정론·네트워크 없음.

임의 임계값 금지: 강수는 기상청 PTY(강수형태) 코드, 대기는 AirKorea khaiGrade(통합지수 등급)
같은 **공식 카테고리**만으로 판정한다. 값이 없으면 unknown(adverse 아님).
"""

from __future__ import annotations

from app.models.environment import AirGrade, EnvironmentContext, Precipitation

# 초단기실황 PTY: 0 없음 / 1 비 / 2 비·눈 / 3 눈 / 5 빗방울 / 6 빗방울·눈날림 / 7 눈날림.
_PTY: dict[str, Precipitation] = {
    "0": Precipitation.NONE,
    "1": Precipitation.RAIN,
    "2": Precipitation.RAIN_SNOW,
    "3": Precipitation.SNOW,
    "5": Precipitation.RAIN,
    "6": Precipitation.RAIN_SNOW,
    "7": Precipitation.SNOW,
}

# AirKorea khaiGrade(통합대기환경지수): 1 좋음 / 2 보통 / 3 나쁨 / 4 매우나쁨.
_KHAI: dict[str, AirGrade] = {
    "1": AirGrade.GOOD,
    "2": AirGrade.MODERATE,
    "3": AirGrade.UNHEALTHY,
    "4": AirGrade.VERY_UNHEALTHY,
}

_WET = {
    Precipitation.RAIN,
    Precipitation.SNOW,
    Precipitation.RAIN_SNOW,
    Precipitation.SHOWER,
}
_BAD_AIR = {AirGrade.UNHEALTHY, AirGrade.VERY_UNHEALTHY}


def precipitation_from_pty(pty: str | None) -> Precipitation:
    if pty is None:
        return Precipitation.UNKNOWN
    return _PTY.get(str(pty).strip(), Precipitation.UNKNOWN)


def air_grade_from_khai(grade: str | None) -> AirGrade:
    if grade is None:
        return AirGrade.UNKNOWN
    return _KHAI.get(str(grade).strip(), AirGrade.UNKNOWN)


def _advisory(precip: Precipitation, air: AirGrade) -> str | None:
    parts: list[str] = []
    if precip in (Precipitation.RAIN, Precipitation.SHOWER):
        parts.append(
            "It's raining near you — indoor experiences may be more comfortable"
        )
    elif precip == Precipitation.SNOW:
        parts.append(
            "It's snowing near you — indoor experiences may be more comfortable"
        )
    elif precip == Precipitation.RAIN_SNOW:
        parts.append(
            "Rain and snow near you — indoor experiences may be more comfortable"
        )
    if air == AirGrade.UNHEALTHY:
        parts.append("air quality is unhealthy today")
    elif air == AirGrade.VERY_UNHEALTHY:
        parts.append("air quality is very unhealthy today")
    if not parts:
        return None
    # 첫 문장은 대문자 시작, 나머지는 '; '로 이어 붙임.
    return "; ".join(parts) + "."


def build_environment(
    pty: str | None, khai: str | None, temp_c: float | None = None
) -> EnvironmentContext:
    precip = precipitation_from_pty(pty)
    air = air_grade_from_khai(khai)
    adverse = precip in _WET or air in _BAD_AIR
    return EnvironmentContext(
        precipitation=precip,
        air_grade=air,
        adverse=adverse,
        advisory=_advisory(precip, air),
        temp_c=temp_c,
    )
