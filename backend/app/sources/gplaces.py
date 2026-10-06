"""Google Places API (New) 클라이언트 — 보조 한정(PRD §6.7).

경량 직접 조회(CLAUDE §4.2): 타임아웃·재시도(tenacity)·단기 TTL 캐시 내장.
- searchText: 이름+좌표 bias 로 장소 1건 매칭 → businessStatus 회수

허용 용도는 §6.7 범위(좌표·주소·링크·이미지 보조)에 더해, 운영 사실인
`businessStatus`(영업중/임시휴업/영구폐업)를 **음성 신호 전용**으로 쓴다
(폐업 확인 시 Hard 제외 — 긍정 생성 아님). `price_level`·평점·리뷰는 사용 금지.

정규화/판정은 하지 않는다(domain/ 담당). 키 미설정·실패는 None 으로 graceful.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
# businessStatus 만 필요 — FieldMask 최소화(과금·페이로드 절감).
_FIELD_MASK = "places.businessStatus,places.location,places.displayName"

# 단기 TTL 캐시. businessStatus 는 자주 변하지 않으나 ToS 상 장기 캐싱 불가 →
# 요청 단위 중복 억제 수준(1시간)만.
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()
_TTL = 3600


def _cache_key(query: str, lat: float, lng: float) -> str:
    return f"{query}@{lat:.4f},{lng:.4f}"


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.3, max=1.5),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
async def _post(client: httpx.AsyncClient, body: dict[str, Any]) -> Any:
    r = await client.post(
        _SEARCH_URL,
        json=body,
        headers={
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        },
    )
    r.raise_for_status()
    return r.json()


async def find_place(
    query: str, lat: float, lng: float, radius_m: int = 200
) -> dict[str, Any] | None:
    """이름+좌표 bias 로 가장 적합한 장소 1건 반환. 키 미설정·실패·0건은 None.

    반환 예: {"businessStatus": "CLOSED_PERMANENTLY",
              "location": {"latitude": .., "longitude": ..},
              "displayName": {"text": ".."}}
    실패를 예외로 올리지 않는다 — 보조 소스 장애가 추천을 막지 않게(§4.2).
    """
    if not settings.google_places_api_key or not query:
        return None

    key = _cache_key(query, lat, lng)
    now = time.time()
    async with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]

    body = {
        "textQuery": query,
        "maxResultCount": 1,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius_m),
            }
        },
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            data = await _post(client, body)
    except httpx.HTTPError:
        return None  # graceful — 보조 소스 실패는 '미확인'으로 흘려보냄

    places = data.get("places") if isinstance(data, dict) else None
    result = places[0] if isinstance(places, list) and places else None

    async with _cache_lock:
        _cache[key] = (now, result)
    return result
