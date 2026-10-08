"""멀티소스 교차 중복 제거 (1d, 설계 §6.2 '병합·dedup').

같은 행사가 TourAPI type 85(축제/공연/행사)와 서울문화포털에 **중복** 올라오는 경우를
결정론적으로 제거한다. 두 소스 제목은 영문(Tour)·국문(Seoul)이라 문자열 매칭이 불가능해
**좌표 근접**을 신호로 쓰되, 오합치(한 장소의 서로 다른 행사·'행사장소 vs 그 안의 행사')를
막기 위해 **TourAPI 쪽이 행사형(type 85=FESTIVAL_EVENT)일 때만** 대상으로 한다.

- 관광지·문화시설(type 76/78)과 서울 행사는 '장소 ≠ 행사'라 합치지 않는다.
- 충돌 시 **TourAPI(기본 정본, CLAUDE §4.2)를 유지**하고 서울 중복만 제거.
- 교차언어 '의미 동일성' 판단은 코드가 brittle → agentic finalize(LLM 선별)로 연기(§6.4).

입력은 `_fetch_pool` 의 원시 풀 dict 리스트(각 항목에 `_src`·`_etype`·`_lat`·`_lng`).
"""

from __future__ import annotations

from app.domain.route import haversine_m
from app.models.recommend import ExperienceType

# 같은 행사로 볼 좌표 근접 임계(m). 소스별 좌표 기록 오차를 감안해 느슨하지 않게 ~100m.
_DUP_RADIUS_M = 100


def _coords(item: dict) -> tuple[float, float] | None:
    lat, lng = item.get("_lat"), item.get("_lng")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def dedup_cross_source(pool: list[dict]) -> tuple[list[dict], int]:
    """TourAPI 행사(type 85)와 좌표 근접한 서울 행사를 중복으로 제거. (정리된 풀, 제거수).

    TourAPI 쪽을 유지한다. 그 외 소스 조합·유형은 건드리지 않는다(보수적).
    """
    tour_events = [
        c
        for it in pool
        if it.get("_src") == "tour"
        and it.get("_etype") == ExperienceType.FESTIVAL_EVENT
        and (c := _coords(it)) is not None
    ]
    if not tour_events:
        return pool, 0

    kept: list[dict] = []
    removed = 0
    for item in pool:
        if item.get("_src") == "seoul":
            sc = _coords(item)
            if sc is not None and any(
                haversine_m(sc[0], sc[1], tc[0], tc[1]) <= _DUP_RADIUS_M
                for tc in tour_events
            ):
                removed += 1
                continue
        kept.append(item)
    return kept, removed
