"""P4 키워드 검색 보강 (_fetch_keyword_pool / _augment_with_keywords) 유닛테스트.

tourapi.search_keyword 를 orchestrator 네임스페이스에서 monkeypatch — 반경 후필터·비문화
제외·좌표없음 drop·contentid dedup·기존 풀 병합을 검증한다. 외부 I/O 없음.
"""

from __future__ import annotations

import asyncio

from app.agent import orchestrator as orch
from app.core.trace import Trace
from app.models.recommend import ParsedConditions


def _kw_item(cid, lat, lng, cat1="A02", cat3="A0201"):
    return {
        "contentid": cid,
        "title": f"T{cid}",
        "mapx": str(lng),
        "mapy": str(lat),
        "contenttypeid": "76",
        "cat1": cat1,
        "cat3": cat3,
        "addr1": "x",
    }


def test_fetch_keyword_pool_filters_and_tags(monkeypatch):
    async def fake_search(term, ctype, rows=10):
        return [
            _kw_item("near", 37.5701, 126.9801),  # 반경 내
            _kw_item("far", 37.70, 127.20),  # 반경 밖 → 제외
            _kw_item("nocoord", None, None),  # 좌표 없음 → drop
            _kw_item("noncult", 37.5702, 126.9802, cat1="A01"),  # 비문화 → 제외
        ]

    monkeypatch.setattr(orch.tourapi, "search_keyword", fake_search)
    pool = asyncio.run(
        orch._fetch_keyword_pool(37.57, 126.98, 1500, ["calligraphy"], Trace())
    )
    ids = {it["contentid"] for it in pool}
    assert ids == {"near"}
    it = pool[0]
    assert it["_src"] == "tour" and it["_lat"] and it["_lng"] and "dist" in it


def test_fetch_keyword_pool_empty_terms(monkeypatch):
    calls = {"n": 0}

    async def fake_search(*a, **k):
        calls["n"] += 1
        return []

    monkeypatch.setattr(orch.tourapi, "search_keyword", fake_search)
    out = asyncio.run(orch._fetch_keyword_pool(37.57, 126.98, 1500, ["  "], Trace()))
    assert out == [] and calls["n"] == 0  # 공백 용어 → 조회 안 함


def test_fetch_keyword_pool_graceful_on_source_error(monkeypatch):
    async def boom(term, ctype, rows=10):
        raise RuntimeError("tourapi down")

    monkeypatch.setattr(orch.tourapi, "search_keyword", boom)
    out = asyncio.run(
        orch._fetch_keyword_pool(37.57, 126.98, 1500, ["calligraphy"], Trace())
    )
    assert out == []  # 실패해도 추천을 막지 않는다


def test_augment_merges_new_skips_existing(monkeypatch):
    existing = [
        {"contentid": "a", "_src": "tour", "dist": 100, "_lat": 37.57, "_lng": 126.98}
    ]

    async def fake_search(term, ctype, rows=10):
        return [_kw_item("a", 37.5701, 126.9801), _kw_item("b", 37.5702, 126.9802)]

    monkeypatch.setattr(orch.tourapi, "search_keyword", fake_search)
    pool = asyncio.run(
        orch._augment_with_keywords(
            existing, 37.57, 126.98, 1500, ParsedConditions(keywords=["x"]), Trace()
        )
    )
    ids = [it["contentid"] for it in pool]
    assert "b" in ids  # 신규 편입
    assert ids.count("a") == 1  # 기존 contentid 중복 안 됨


def test_augment_noop_without_keywords(monkeypatch):
    calls = {"n": 0}

    async def fake_search(*a, **k):
        calls["n"] += 1
        return []

    monkeypatch.setattr(orch.tourapi, "search_keyword", fake_search)
    pool = [{"contentid": "a", "_src": "tour"}]
    out = asyncio.run(
        orch._augment_with_keywords(
            pool, 37.57, 126.98, 1500, ParsedConditions(), Trace()
        )
    )
    assert out is pool and calls["n"] == 0  # 키워드 없으면 조회조차 안 함
