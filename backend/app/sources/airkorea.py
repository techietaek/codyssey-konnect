"""AirKorea 실시간 대기질 클라이언트 (data.go.kr, PRD §6.6 Context).

서울 시도 실시간 측정소들의 통합대기환경지수 등급(khaiGrade)을 조회해 대표 등급을 돌려준다.
환경은 Context일 뿐 — 운영 사실 판정에 쓰지 않는다. 실패/미확보는 None(graceful).
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

_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
_TIMEOUT = httpx.Timeout(6.0, connect=4.0)


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


async def khai_grade(sido: str = "서울") -> str | None:
    """시도 실시간 측정소들의 khaiGrade 대표값(평균 등급, '1'~'4'). 실패/없음은 None."""
    params = {
        "serviceKey": settings.data_go_kr_service_key,
        "returnType": "json",
        "numOfRows": 100,
        "pageNo": 1,
        "sidoName": sido,
        "ver": "1.3",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await _get(client, params)
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    items = ((data.get("response") or {}).get("body") or {}).get("items") or []
    grades = [
        int(g)
        for it in items
        if (g := str(it.get("khaiGrade") or "").strip()) in ("1", "2", "3", "4")
    ]
    return str(round(sum(grades) / len(grades))) if grades else None
