"""서울문화포털 문화행사 API (서울 열린데이터광장 culturalEventInfo) 클라이언트.

경량 직접 조회(CLAUDE §4.2): 타임아웃·재시도(tenacity)·단기 TTL 캐시 내장.
- culturalEventInfo: 날짜 필터로 '그 날 열리는' 문화행사 목록(제목·기간·좌표·요금·링크·이미지)

행사 row 는 목록 응답에 모든 필드가 들어있어 TourAPI 처럼 상세 2차 조회가 필요 없다.
정규화/판정은 하지 않는다(domain/ 담당). 실패는 ExternalSourceError 로 변환.

좌표 주의: 이 API 는 LOT(위도)·LAT(경도)로 이름이 관례와 뒤바뀌어 있어, 정규화 단계에서
값 범위로 안전 할당한다(domain/normalize._valid_seoul_coords).
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.core.exceptions import ExternalSourceError

_BASE = "http://openapi.seoul.go.kr:8088"
_SERVICE = "culturalEventInfo"
_TIMEOUT = httpx.Timeout(6.0, connect=4.0)

# 단기 TTL 캐시 (경량 조회 방어, NFR-03). 행사 목록은 날짜 단위라 10분이면 충분.
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()
_TTL_LIST = 600

_OK_CODES = ("INFO-000",)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=2),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
async def _get(client: httpx.AsyncClient, url: str) -> Any:
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


async def cultural_events(
    on_date: date, start: int = 1, end: int = 100
) -> list[dict[str, Any]]:
    """방문일에 열리는 문화행사 목록. DATE 필터로 서버가 기간 포함분만 돌려준다.

    경로 포지셔널 파라미터: /{KEY}/json/{SERVICE}/{START}/{END}/{CODENAME}/{TITLE}/{DATE}
    CODENAME·TITLE 은 비워두고(공백) DATE 만 지정한다.
    """
    key = settings.seoul_openapi_key
    if not key:
        raise ExternalSourceError("Seoul OpenAPI key not configured")

    date_str = on_date.isoformat()  # YYYY-MM-DD
    # CODENAME·TITLE 자리는 빈 문자열로 둘 수 없어 공백 1칸을 인코딩해 채운다.
    blank = quote(" ")
    url = (
        f"{_BASE}/{key}/json/{_SERVICE}/{start}/{end}/{blank}/{blank}/"
        f"{quote(date_str)}"
    )

    cache_key = f"{_SERVICE}:{date_str}:{start}-{end}"
    now = time.time()
    async with _cache_lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < _TTL_LIST:
            return hit[1]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            data = await _get(client, url)
    except httpx.HTTPError as e:
        raise ExternalSourceError("Seoul culturalEventInfo request failed") from e

    body = data.get(_SERVICE) or {}
    result = body.get("RESULT") or {}
    code = str(result.get("CODE") or "")
    # INFO-200 = 해당 데이터 없음(정상 0건). 그 외 비정상 코드는 소스 오류로 본다.
    if code == "INFO-200":
        rows: list[dict[str, Any]] = []
    elif code in _OK_CODES:
        raw = body.get("row") or []
        rows = raw if isinstance(raw, list) else [raw]
    else:
        raise ExternalSourceError(f"Seoul culturalEventInfo error code={code}")

    async with _cache_lock:
        _cache[cache_key] = (now, rows)
    return rows
