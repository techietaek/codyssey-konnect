"""장소 실내/외 분류 (classify_places, rollout 4 · 설계 §6.4).

TourAPI 는 실내/외를 신뢰성 있게 주지 않는다. 유형 휴리스틱(박물관=실내·공원=실외)은
탑골공원·김치간 등에서 오분류가 났다. 그래서 각 후보의 **공식 텍스트(제목+overview)** 를
LLM 이 읽고 per-place 로 실내/외를 분류한다(해석이지 사실 생성 아님 — 가격·시간엔 관여 안 함).

- 반환: {id: "indoor"|"outdoor"|"unknown"}. 애매하면 unknown(확신 없을 때 Hard 제외 금지).
- graceful: 실패/빈 입력은 빈 dict(= 전부 unknown 취급 → 유형 휴리스틱 fallback).
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import settings
from app.core.trace import Trace

logger = logging.getLogger("konnect.agent")

Setting = Literal["indoor", "outdoor", "unknown"]


class _PlaceIO(BaseModel):
    id: str = Field(description="The candidate id exactly as given.")
    setting: Setting = Field(
        description="indoor = primarily enclosed (museums, galleries, indoor halls). "
        "outdoor = primarily open-air (parks, palace grounds, outdoor markets, street "
        "festivals). unknown = the text does not make it clear. Base ONLY on the provided "
        "text; when unsure, use unknown."
    )


class PlaceClassification(BaseModel):
    places: list[_PlaceIO] = Field(default_factory=list)


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "Classify each place as indoor, outdoor, or unknown for a traveler deciding "
                "where to go. Judge only from the name and official description provided — do "
                "not use outside knowledge or guess. If a place is a mix or the text is "
                "unclear, use unknown."
            ),
        ),
        ("human", "Places:\n{candidates}"),
    ]
)


async def classify_places(
    items: list[tuple[str, str]], trace: Trace
) -> dict[str, Setting]:
    """후보 (id, text) → {id: indoor|outdoor|unknown}. 실패/빈 입력은 {}(전부 unknown)."""
    if not items:
        return {}
    valid_ids = {i for i, _ in items}
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=20,
        )
        chain = _PROMPT | llm.with_structured_output(PlaceClassification)
        payload = "\n".join(f"- id={i}: {text}" for i, text in items)
        res = await chain.ainvoke({"candidates": payload})
        verdicts = {p.id: p.setting for p in res.places if p.id in valid_ids}
        trace.step(
            "classify_places",
            classified=len(verdicts),
            indoor=sum(1 for v in verdicts.values() if v == "indoor"),
            outdoor=sum(1 for v in verdicts.values() if v == "outdoor"),
        )
        return verdicts
    except Exception as e:  # noqa: BLE001
        # 분류 실패가 추천을 막지 않는다 — 전부 unknown 취급(유형 휴리스틱 fallback).
        logger.warning("classify_places failed: %s", type(e).__name__)
        return {}
