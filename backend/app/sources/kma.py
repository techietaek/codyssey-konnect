"""기상청 초단기실황 클라이언트 (data.go.kr, PRD §6.6 Context).

현재 강수형태(PTY)·기온(T1H)만 가볍게 조회한다. 환경은 Context일 뿐 — 운영 사실 판정에
쓰지 않는다. 실패/미확보는 빈 dict(graceful) → 환경 unknown(adverse 아님).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
_TIMEOUT = httpx.Timeout(6.0, connect=4.0)
_KST = timezone(timedelta(hours=9))


def _grid(lat: float, lon: float) -> tuple[int, int]:
    """위경도 → 기상청 격자(nx, ny). KMA 표준 LCC 변환."""
    re_, grid = 6371.00877, 5.0
    slat1, slat2 = math.radians(30.0), math.radians(60.0)
    olon, olat = math.radians(126.0), math.radians(38.0)
    xo, yo = 43, 136
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re_ / grid * sf / math.pow(ro, sn)
    ra = math.tan(math.pi * 0.25 + math.radians(lat) * 0.5)
    ra = re_ / grid * sf / math.pow(ra, sn)
    theta = math.radians(lon) - olon
    if theta > math.pi:
        theta -= 2 * math.pi
    if theta < -math.pi:
        theta += 2 * math.pi
    theta *= sn
    nx = int(ra * math.sin(theta) + xo + 0.5)
    ny = int(ro - ra * math.cos(theta) + yo + 0.5)
    return nx, ny


def _base() -> tuple[str, str]:
    """초단기실황 base_date/base_time (매시 40분 이후 제공 → 그 전이면 직전 시각)."""
    now = datetime.now(_KST)
    if now.minute < 40:
        now -= timedelta(hours=1)
    return now.strftime("%Y%m%d"), now.strftime("%H00")


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
async def _get(client: httpx.AsyncClient, params: dict[str, Any]) -> httpx.Response:
    r = await client.get(_URL, params=params)
    r.raise_for_status()
    return r


async def ultra_ncst(lat: float, lon: float) -> dict[str, str]:
    """초단기실황 category→value (예: {'PTY':'1','T1H':'8.0'}). 실패/미확보는 {}."""
    nx, ny = _grid(lat, lon)
    base_date, base_time = _base()
    params = {
        "serviceKey": settings.data_go_kr_service_key,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await _get(client, params)
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return {}

    body = ((data.get("response") or {}).get("body")) or {}
    items = (body.get("items") or {}).get("item") or []
    return {
        str(it.get("category")): str(it.get("obsrValue"))
        for it in items
        if it.get("category") is not None
    }
