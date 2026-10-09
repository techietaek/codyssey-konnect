"""의미 기반 selection 랭킹 (P2, docs/recommendation-and-search-quality.md §7).

문제(L2·L3): 사용자 note/open_preferences 의 의미가 '검색·선발'이 아니라 '조회 후 재정렬'
에만 반영돼, 상세조회 컷(pool[:K]) 전에 관련도가 작동하지 못한다. P2 는 **목록 단계 텍스트**
(제목·주소·분류 — 상세조회 전 값)를 사용자 의도와 임베딩 유사도로 비교해, **어떤 후보를
상세조회·판정할지**를 거리·enum 만이 아니라 의미 관련도로도 정하게 한다.

신뢰 경계(불변):
- 임베딩은 **순서(ordering)만** 바꾼다 — 사실·가용성·가격·시간을 생성·수정하지 않는다.
- 실패/빈 의도는 graceful: 유사도 0(= 기존 거리·enum 순서 그대로). 추천을 막지 않는다.
- 보조 경량 모델 경계(§6.7)와 동일 선상 — OpenAI Embeddings(text-embedding-3-small) 재사용.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from app.core.trace import Trace
from app.models.recommend import InterestCode, ParsedConditions
from app.rag.embed import embed_documents, embed_query

logger = logging.getLogger("konnect.agent")

# enum 관심사 → 임베딩용 사람이 읽는 구절(검색 의도 보강). 사실 생성 아님(의도 표현).
_INTEREST_WORDS: dict[InterestCode, str] = {
    InterestCode.TRADITIONAL: "traditional Korean culture",
    InterestCode.PALACES_HISTORIC: "palaces and historic sites",
    InterestCode.HANDS_ON: "hands-on experiences and crafts",
    InterestCode.ART_EXHIBITIONS: "art exhibitions and galleries",
    InterestCode.LIVE_PERFORMANCES: "live performances",
    InterestCode.FESTIVALS_EVENTS: "festivals and events",
}


def build_intent_text(cond: ParsedConditions, note: str | None) -> str | None:
    """사용자 의도를 임베딩할 한 문자열로 합성. 신호가 전혀 없으면 None(의미랭킹 생략).

    note 원문 + 관심사(enum→구절) + 개방형 긍정 선호를 순서 보존 dedup 으로 잇는다.
    비선호/배제는 넣지 않는다(그건 별도 Hard/Soft 경로가 담당 — 여기선 '원하는 것'만).
    """
    parts: list[str] = []
    if note and note.strip():
        parts.append(note.strip())
    parts += [_INTEREST_WORDS[i] for i in cond.interests if i in _INTEREST_WORDS]
    parts += [p for p in cond.open_preferences if p and p.strip()]
    deduped = list(dict.fromkeys(p.strip() for p in parts if p and p.strip()))
    text = ". ".join(deduped)
    return text or None


def pool_item_text(it: dict[str, Any]) -> str:
    """목록 단계(상세조회 전) 후보의 의미 비교용 텍스트. 공식 목록 필드만 — 생성 없음.

    tour: title + addr1(지역 맥락). seoul: TITLE + CODENAME(분류) + PLACE/GUNAME.
    상세 overview 는 아직 없으므로(비싼 2차 조회 전) 얇지만, 선발 관련도엔 충분히 유효.
    """
    if it.get("_src") == "seoul":
        parts = [it.get("TITLE"), it.get("CODENAME"), it.get("PLACE"), it.get("GUNAME")]
    else:
        parts = [it.get("title"), it.get("addr1")]
    joined = " · ".join(str(p).strip() for p in parts if p and str(p).strip())
    return joined[:200]


def _cosine(a: list[float], b: list[float]) -> float:
    """코사인 유사도. 0-노름 방어(0 반환)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


async def semantic_similarities(
    texts: list[str], intent: str | None, trace: Trace
) -> list[float]:
    """pool 텍스트별 의도 유사도(코사인) 정렬-정렬 리스트. 의도 없음/실패는 전부 0.0(graceful).

    쿼리·문서 임베딩을 병렬 1회씩 — 상세조회(TourAPI×N)보다 훨씬 싸다. 순서 보존.
    """
    if not intent or not texts:
        return [0.0] * len(texts)
    try:
        qvec, dvecs = await asyncio.gather(embed_query(intent), embed_documents(texts))
        sims = [_cosine(qvec, d) for d in dvecs]
        trace.step(
            "semantic_rank",
            items=len(texts),
            intent=intent[:80],
            top=round(max(sims), 3) if sims else None,
        )
        return sims
    except Exception as e:  # noqa: BLE001 — 임베딩 실패가 추천을 막지 않는다
        logger.warning("semantic rank failed: %s", type(e).__name__)
        trace.step("semantic_rank_error", error=type(e).__name__)
        return [0.0] * len(texts)
