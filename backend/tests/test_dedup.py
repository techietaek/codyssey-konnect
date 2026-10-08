"""멀티소스 교차 dedup 단위 테스트 (1d).

규칙: TourAPI type 85(FESTIVAL_EVENT)와 좌표 ~100m 내인 서울 행사만 중복 제거(서울 제거,
TourAPI 유지). 관광지·시설(76/78)과는 합치지 않고, 좌표 먼 행사는 유지한다.
"""

from __future__ import annotations

from app.domain.dedup import dedup_cross_source
from app.models.recommend import ExperienceType


def _tour(etype, lat, lng, cid="t1"):
    return {
        "_src": "tour",
        "_etype": etype,
        "_lat": lat,
        "_lng": lng,
        "contentid": cid,
    }


def _seoul(lat, lng, title="행사"):
    return {
        "_src": "seoul",
        "_etype": ExperienceType.FESTIVAL_EVENT,
        "_lat": lat,
        "_lng": lng,
        "TITLE": title,
    }


def test_removes_seoul_dup_near_tour_festival():
    pool = [
        _tour(ExperienceType.FESTIVAL_EVENT, 37.5700, 126.9800),
        _seoul(37.5701, 126.9800),  # ~11m → 중복
    ]
    kept, removed = dedup_cross_source(pool)
    assert removed == 1
    assert [k["_src"] for k in kept] == ["tour"]  # TourAPI 유지


def test_keeps_seoul_far_from_tour_festival():
    pool = [
        _tour(ExperienceType.FESTIVAL_EVENT, 37.5700, 126.9800),
        _seoul(37.5900, 126.9800),  # ~2km → 유지
    ]
    kept, removed = dedup_cross_source(pool)
    assert removed == 0
    assert len(kept) == 2


def test_does_not_merge_with_attraction_or_facility():
    # 관광지(76)·시설(78) 근처 서울 행사는 '장소≠행사'라 유지
    pool = [
        _tour(ExperienceType.HISTORIC_VISIT, 37.5700, 126.9800, cid="a"),
        _tour(ExperienceType.EXHIBITION, 37.5700, 126.9800, cid="b"),
        _seoul(37.5700, 126.9800),
    ]
    kept, removed = dedup_cross_source(pool)
    assert removed == 0
    assert len(kept) == 3


def test_no_tour_events_returns_unchanged():
    pool = [_seoul(37.57, 126.98), _seoul(37.58, 126.99)]
    kept, removed = dedup_cross_source(pool)
    assert removed == 0
    assert kept == pool


def test_missing_coords_not_deduped():
    pool = [
        _tour(ExperienceType.FESTIVAL_EVENT, 37.5700, 126.9800),
        {
            "_src": "seoul",
            "_etype": ExperienceType.FESTIVAL_EVENT,
            "_lat": None,
            "_lng": None,
            "TITLE": "좌표없음",
        },
    ]
    kept, removed = dedup_cross_source(pool)
    assert removed == 0
    assert len(kept) == 2


def test_tour_items_never_removed():
    # 두 TourAPI 행사가 같은 좌표여도 교차 dedup 대상 아님(동일 소스 id dedup 은 fetch 단계)
    pool = [
        _tour(ExperienceType.FESTIVAL_EVENT, 37.57, 126.98, cid="a"),
        _tour(ExperienceType.FESTIVAL_EVENT, 37.57, 126.98, cid="b"),
    ]
    kept, removed = dedup_cross_source(pool)
    assert removed == 0
    assert len(kept) == 2
