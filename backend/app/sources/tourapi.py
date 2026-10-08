"""TourAPI (한국관광공사 EngService2) 클라이언트.

경량 직접 조회(CLAUDE §4.2): 타임아웃·재시도(tenacity) 내장. 응답 캐싱은 하지 않는다
(API 정책·데이터 신선도 — 매 요청 직접 조회).
- locationBasedList2: 좌표 기반 후보 발견(title·좌표·type·dist·image)
- detailIntro2: 타입별 운영시간·요금·휴무 (list에는 없음)
- detailCommon2: homepage(공식 링크)·overview

정규화/판정은 하지 않는다(domain/ 담당). 실패는 ExternalSourceError 로 변환.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.core.exceptions import ExternalSourceError

_BASE = "https://apis.data.go.kr/B551011/EngService2"
_COMMON = {"MobileOS": "ETC", "MobileApp": "KONNECT", "_type": "json"}
_TIMEOUT = httpx.Timeout(6.0, connect=4.0)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
async def _get(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> Any:
    r = await client.get(f"{_BASE}/{path}", params=params)
    r.raise_for_status()
    return r.json()


async def _call(path: str, params: dict[str, Any]) -> Any:
    full = {**_COMMON, "serviceKey": settings.data_go_kr_service_key, **params}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            data = await _get(client, path, full)
    except httpx.HTTPError as e:
        raise ExternalSourceError(f"TourAPI {path} request failed") from e

    header = (data.get("response") or {}).get("header") or {}
    if str(header.get("resultCode")) not in ("0000", "00"):
        raise ExternalSourceError(
            f"TourAPI {path} error resultCode={header.get('resultCode')}"
        )
    return data


def _items(data: Any) -> list[dict[str, Any]]:
    """응답에서 item 리스트 추출. 0건이면 items 가 빈 문자열 → []."""
    body = (data.get("response") or {}).get("body") or {}
    items = body.get("items")
    if not items or not isinstance(items, dict):
        return []
    it = items.get("item") or []
    return it if isinstance(it, list) else [it]


async def location_based_list(
    lat: float, lng: float, radius: int, content_type_id: int, rows: int = 10
) -> list[dict[str, Any]]:
    """좌표 반경 내 후보 목록(거리순). mapX=경도, mapY=위도."""
    data = await _call(
        "locationBasedList2",
        {
            "numOfRows": rows,
            "pageNo": 1,
            "arrange": "E",  # 거리순
            "mapX": f"{lng}",
            "mapY": f"{lat}",
            "radius": radius,
            "contentTypeId": content_type_id,
        },
    )
    return _items(data)


async def detail_intro(content_id: str, content_type_id: str) -> dict[str, Any]:
    """타입별 상세(운영시간·요금·휴무)."""
    data = await _call(
        "detailIntro2",
        {"contentId": content_id, "contentTypeId": content_type_id},
    )
    items = _items(data)
    return items[0] if items else {}


async def detail_common(content_id: str) -> dict[str, Any]:
    """공통 상세(homepage·overview)."""
    data = await _call("detailCommon2", {"contentId": content_id})
    items = _items(data)
    return items[0] if items else {}


async def detail_info(content_id: str, content_type_id: str) -> list[dict[str, Any]]:
    """반복 구조정보(infoname/infotext 행). detailIntro2 가 놓치는 입장료·운영시간을
    별도 행으로 담는 경우가 많다(예: infoname='Admission Fees'). 행 목록을 그대로 반환."""
    data = await _call(
        "detailInfo2",
        {"contentId": content_id, "contentTypeId": content_type_id},
    )
    return _items(data)
