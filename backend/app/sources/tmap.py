"""Tmap 보행자 경로 클라이언트 (백엔드 프록시, PRD §7).

도보 거리(m)·소요시간(예상)·경로선 좌표를 반환한다. 임의 직선은 만들지 않는다 —
Tmap이 준 실제 경로만 쓰고, 실패 시 None(프론트가 'Route unavailable'로 폴백).

provenance: 도보시간은 '예상값(estimate)'이지 실제 ETA 보장이 아니다(PRD §6.2).
"""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

_URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1&format=json"
_TIMEOUT = httpx.Timeout(6.0, connect=4.0)

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()
_TTL = 1800  # 30분 (도보 경로는 자주 안 변함 + 호출 제한 방어)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
async def _post(client: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    r = await client.post(
        _URL,
        json=body,
        headers={"appKey": settings.tmap_api_key, "Content-Type": "application/json"},
    )
    r.raise_for_status()
    return r


async def pedestrian_route(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> dict[str, Any] | None:
    """도보 경로. 성공 시 {distance_m, walk_minutes, path:[[lat,lng],...]}, 실패 시 None."""
    key = f"{start_lat:.5f},{start_lng:.5f}->{end_lat:.5f},{end_lng:.5f}"
    now = _time.time()
    async with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]

    body = {
        "startX": f"{start_lng}",
        "startY": f"{start_lat}",
        "endX": f"{end_lng}",
        "endY": f"{end_lat}",
        "startName": "start",
        "endName": "end",
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await _post(client, body)
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None  # 한 구간 실패가 전체 추천을 막지 않는다 → 프론트 폴백

    feats = data.get("features") or []
    if not feats:
        return None
    props = feats[0].get("properties") or {}
    dist = props.get("totalDistance")
    secs = props.get("totalTime")
    if dist is None or secs is None:
        return None

    path: list[list[float]] = []
    for f in feats:
        g = f.get("geometry") or {}
        if g.get("type") == "LineString":
            for lng, lat in g.get("coordinates", []):
                path.append([lat, lng])

    result = {
        "distance_m": int(dist),
        "walk_minutes": max(1, round(int(secs) / 60)),
        "path": path,
    }
    async with _cache_lock:
        _cache[key] = (now, result)
    return result
