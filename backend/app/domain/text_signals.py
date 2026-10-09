"""원본 메시지에서 결정론적으로 뽑는 신호 (실내/외) — 2-LLM 추출의 신호 유실 보완.

챗 경로는 [LLM#1 라우터→preferences] → [LLM#2 note_parser→구조화] 2단을 거쳐, #1이
preferences 로 요약하며 'indoor' 같은 핵심 신호를 흘리면 충돌 되묻기·실내외 랭킹이 깨진다
(docs/llm-prompts-inventory.md). 여기서 **원본 사용자 메시지**를 직접 보고 명시적 실내/외
표현만 결정론으로 집어낸다 — LLM 생성이 아니라 문구 매칭이라 신뢰경계 불변.

보수적 규칙: 명시 표현만 잡고 모호하면 None. 부정("no outdoor"=실내)을 먼저 처리한다.
"""

from __future__ import annotations

from typing import Literal

IO = Literal["indoor", "outdoor"]

# strict/부정 표현(실제 선호를 결정) — 평이한 키워드보다 먼저 검사한다.
#   "no outdoor"/"nothing outdoors" 는 실내(strict), 그 반대도 마찬가지.
_INDOOR_STRICT = (
    "indoor only",
    "only indoor",
    "indoors only",
    "strictly indoor",
    "nothing outdoor",
    "nothing outdoors",
    "no outdoor",
    "not outdoor",
)
_OUTDOOR_STRICT = (
    "outdoor only",
    "only outdoor",
    "outdoors only",
    "strictly outdoor",
    "nothing indoor",
    "nothing indoors",
    "no indoor",
    "not indoor",
)
# 평이한 선호 표현(약한 신호). "inside/outside" 는 오매칭(예: "inside the palace") 위험이라 제외.
_INDOOR = ("indoor", "indoors")
_OUTDOOR = ("outdoor", "outdoors", "open-air", "open air")


def detect_indoor_outdoor(text: str | None) -> tuple[IO | None, bool]:
    """(선호, strict) 반환. 명시 표현이 없거나 모호(양쪽 다 언급)면 (None, False).

    strict=True 는 배타 표현("indoor only", "no outdoor" 등). 평이한 "indoor" 는 strict=False.
    """
    if not text:
        return None, False
    low = text.lower()
    if any(p in low for p in _INDOOR_STRICT):
        return "indoor", True
    if any(p in low for p in _OUTDOOR_STRICT):
        return "outdoor", True
    indoor = any(p in low for p in _INDOOR)
    outdoor = any(p in low for p in _OUTDOOR)
    if indoor and outdoor:
        return None, False  # 둘 다 언급 → 모호, 지어내지 않는다
    if indoor:
        return "indoor", False
    if outdoor:
        return "outdoor", False
    return None, False
