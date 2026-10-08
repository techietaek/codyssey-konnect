"""장소 per-candidate LLM 판정 (classify_places, rollout 4·4b · 설계 §6.4).

TourAPI 는 실내/외를 신뢰성 있게 주지 않고, "조용한/로맨틱한" 같은 개방형 정성 선호는
데이터에 없다. 그래서 각 후보의 **공식 텍스트(제목+overview)** 를 LLM 이 읽고 **한 콜에서**:
- 실내/외(indoor|outdoor|unknown) 분류,
- 사용자의 개방형 긍정 선호(open_preferences) 적합 여부(Soft 랭킹용),
를 per-candidate 로 돌려준다. 해석이지 사실 생성 아님 — 가격·시간엔 관여하지 않는다.
별도 finalize LLM 콜을 추가하지 않고 이 콜에 정성 적합도를 겸한다(콜 수 0 증가).

- 애매한 실내/외는 unknown(확신 없을 때 Hard 제외 금지). 선호 없으면 fits_vibe=True(중립).
- graceful: 실패/빈 입력은 {} (전부 unknown·중립 → 유형 휴리스틱 fallback).
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


class PlaceVerdict(BaseModel):
    id: str = Field(description="The candidate id exactly as given.")
    setting: Setting = Field(
        description="indoor = primarily enclosed (museums, galleries, indoor halls). "
        "outdoor = primarily open-air (parks, palace grounds, outdoor markets, street "
        "festivals). unknown = the text does not make it clear. Base ONLY on the provided "
        "text; when unsure, use unknown."
    )
    fits_vibe: bool = Field(
        default=True,
        description="True if the place plausibly matches ALL of the traveler's requested "
        "qualities; False if it clearly does not. If no qualities were requested, always True. "
        "Judge only from the provided text; when unsure, True (do not penalize).",
    )


class PlaceClassification(BaseModel):
    places: list[PlaceVerdict] = Field(default_factory=list)


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "For each place, (1) classify indoor, outdoor, or unknown, and (2) if the "
                "traveler asked for qualities, judge whether it fits them. Judge ONLY from the "
                "name and official description provided — no outside knowledge, no guessing. "
                "If a place is a mix or the text is unclear, use unknown for setting; when "
                "unsure about fit, keep fits_vibe true (soft ranking, never exclude on a guess)."
            ),
        ),
        (
            "human",
            "Traveler's requested qualities: {vibe}\n\nPlaces:\n{candidates}",
        ),
    ]
)


async def classify_places(
    items: list[tuple[str, str]],
    trace: Trace,
    open_preferences: list[str] | None = None,
) -> dict[str, PlaceVerdict]:
    """후보 (id, text) → {id: PlaceVerdict(setting, fits_vibe)}. 실패/빈 입력은 {}.

    open_preferences(개방형 긍정 선호)가 있으면 fits_vibe 를 그에 맞춰 판정(Soft), 없으면 중립.
    """
    if not items:
        return {}
    valid_ids = {i for i, _ in items}
    vibe = ", ".join(open_preferences) if open_preferences else "(none)"
    try:
        llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
            timeout=20,
        )
        chain = _PROMPT | llm.with_structured_output(PlaceClassification)
        payload = "\n".join(f"- id={i}: {text}" for i, text in items)
        res = await chain.ainvoke({"candidates": payload, "vibe": vibe})
        verdicts = {p.id: p for p in res.places if p.id in valid_ids}
        trace.step(
            "classify_places",
            classified=len(verdicts),
            indoor=sum(1 for v in verdicts.values() if v.setting == "indoor"),
            outdoor=sum(1 for v in verdicts.values() if v.setting == "outdoor"),
            vibe=vibe,
            misfit=sum(1 for v in verdicts.values() if not v.fits_vibe),
        )
        return verdicts
    except Exception as e:  # noqa: BLE001
        # 분류 실패가 추천을 막지 않는다 — 전부 unknown·중립 취급(유형 휴리스틱 fallback).
        logger.warning("classify_places failed: %s", type(e).__name__)
        return {}
