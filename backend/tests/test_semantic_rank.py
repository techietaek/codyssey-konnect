"""semantic_rank (P2) 유닛테스트 — 순수 헬퍼 + embed 모킹.

임베딩은 실제 호출하지 않는다(모듈 네임스페이스 monkeypatch). 신뢰 경계상 'graceful=유사도 0'
(실패·빈 의도 → 기존 순서 보존)과 의미 랭킹이 순서만 바꾸는지를 검증한다.
"""

from __future__ import annotations

import asyncio

from app.agent import semantic_rank as sr
from app.core.trace import Trace
from app.models.recommend import InterestCode, ParsedConditions


def test_build_intent_text_combines_and_dedups():
    cond = ParsedConditions(
        interests=[InterestCode.PALACES_HISTORIC],
        open_preferences=["quiet"],
    )
    text = sr.build_intent_text(cond, "I want a calm palace visit")
    assert text is not None
    assert "calm palace visit" in text
    assert "palaces and historic sites" in text
    assert "quiet" in text


def test_build_intent_text_none_when_no_signal():
    assert sr.build_intent_text(ParsedConditions(), None) is None
    assert sr.build_intent_text(ParsedConditions(), "   ") is None


def test_build_intent_text_excludes_avoid_and_exclude():
    # 비선호/배제는 의도(원하는 것)에 넣지 않는다 — 별도 경로 담당.
    cond = ParsedConditions(
        avoid_interests=[InterestCode.LIVE_PERFORMANCES],
        exclude_concepts=["museums"],
    )
    assert sr.build_intent_text(cond, None) is None


def test_pool_item_text_sources():
    tour = {"title": "Gyeongbokgung Palace", "addr1": "Jongno-gu, Seoul"}
    assert "Gyeongbokgung Palace" in sr.pool_item_text(tour)
    assert "Jongno-gu" in sr.pool_item_text(tour)
    seoul = {
        "_src": "seoul",
        "TITLE": "한복 체험",
        "CODENAME": "교육/체험",
        "PLACE": "북촌",
    }
    txt = sr.pool_item_text(seoul)
    assert "한복 체험" in txt and "교육/체험" in txt and "북촌" in txt


def test_pool_item_text_handles_missing_fields():
    assert sr.pool_item_text({}) == ""
    assert sr.pool_item_text({"title": "A"}) == "A"


def test_cosine_bounds():
    assert sr._cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert sr._cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert sr._cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # 0-노름 방어


def test_semantic_similarities_no_intent_returns_zeros():
    out = asyncio.run(sr.semantic_similarities(["a", "b", "c"], None, Trace()))
    assert out == [0.0, 0.0, 0.0]


def test_semantic_similarities_ranks_by_cosine(monkeypatch):
    # 의도 벡터 = [1,0]; 문서 = [정렬·직교·반대] → 유사도 1, 0, -1 순.
    async def fake_q(text):
        return [1.0, 0.0]

    async def fake_docs(texts):
        return [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]

    monkeypatch.setattr(sr, "embed_query", fake_q)
    monkeypatch.setattr(sr, "embed_documents", fake_docs)
    sims = asyncio.run(sr.semantic_similarities(["x", "y", "z"], "intent", Trace()))
    assert sims[0] > sims[1] > sims[2]
    assert sims[0] == 1.0 and sims[1] == 0.0 and sims[2] == -1.0


def test_semantic_similarities_graceful_on_failure(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("embedding service down")

    monkeypatch.setattr(sr, "embed_query", boom)
    monkeypatch.setattr(sr, "embed_documents", boom)
    out = asyncio.run(sr.semantic_similarities(["a", "b"], "intent", Trace()))
    assert out == [0.0, 0.0]  # 실패해도 추천을 막지 않는다
