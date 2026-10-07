"""환경 Context 조립 — 기상청 + AirKorea 조회 → 정규화 (PRD §6.6).

두 소스를 병렬로 가볍게 조회하고 domain/environment 로 정규화한다. 어느 쪽이 실패해도
추천을 막지 않는다(graceful) — 미확보 축은 unknown 으로 남는다. 환경은 Soft Context다.
"""

from __future__ import annotations

import asyncio

from app.core.trace import Trace
from app.domain.environment import build_environment
from app.models.environment import EnvironmentContext
from app.sources import airkorea, kma


async def get_environment(lat: float, lng: float, trace: Trace) -> EnvironmentContext:
    ncst, khai = await asyncio.gather(
        kma.ultra_ncst(lat, lng), airkorea.khai_grade(), return_exceptions=True
    )
    ncst = ncst if isinstance(ncst, dict) else {}
    khai = khai if isinstance(khai, str) else None

    temp: float | None = None
    raw_t = ncst.get("T1H")
    if raw_t not in (None, ""):
        try:
            temp = float(raw_t)
        except ValueError:
            temp = None

    env = build_environment(ncst.get("PTY"), khai, temp)
    trace.step(
        "environment",
        precip=env.precipitation.value,
        air=env.air_grade.value,
        adverse=env.adverse,
    )
    return env
