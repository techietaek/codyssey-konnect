"""입력 내용 충돌 감지 (실내/실외 선호 ↔ 관심사).

사용자가 "indoor" 를 원하면서 본질적으로 실외인 관심사(궁궐·역사장소·축제)를 함께 말하면
요청이 서로 모순된다. 이때 조용히 한쪽을 버리지 않고(기존 동작은 실내를 우선해 궁궐을
제외했다) **되물어** 사용자 의도를 확정한다(Request 우선 — 사용자 프롬프트가 최우선).

판정은 결정론 코드. 어떤 사실도 만들지 않으며, 관심사 enum ↔ 실내/외 성향 매핑만 본다.
"""

from __future__ import annotations

from app.models.recommend import InterestCode, ParsedConditions

# 본질적으로 실외인 관심사(궁궐·역사장소=야외 경내, 축제=야외 행사).
_OUTDOOR_INTERESTS = {InterestCode.PALACES_HISTORIC, InterestCode.FESTIVALS_EVENTS}
# 본질적으로 실내인 관심사(전시·미술관, 체험·공방).
_INDOOR_INTERESTS = {InterestCode.ART_EXHIBITIONS, InterestCode.HANDS_ON}


def io_interest_conflict(cond: ParsedConditions) -> list[InterestCode]:
    """실내/외 선호와 모순되는 관심사 목록을 반환(없으면 빈 리스트).

    - indoor 선호 + 실외 관심사(궁궐·축제) → 그 실외 관심사들.
    - outdoor 선호 + 실내 관심사(전시·체험) → 그 실내 관심사들.
    (traditional·live_performances 처럼 양쪽/중립인 관심사는 충돌로 보지 않는다.)
    """
    pref = cond.indoor_outdoor
    if pref == "indoor":
        return [i for i in cond.interests if i in _OUTDOOR_INTERESTS]
    if pref == "outdoor":
        return [i for i in cond.interests if i in _INDOOR_INTERESTS]
    return []


# 사용자-facing 라벨(내부 enum 노출 금지 — CLAUDE §5). 충돌 안내 문구 합성용.
_INTEREST_LABEL = {
    InterestCode.PALACES_HISTORIC: "palaces & historic sites",
    InterestCode.FESTIVALS_EVENTS: "festivals & outdoor events",
    InterestCode.ART_EXHIBITIONS: "art exhibitions & galleries",
    InterestCode.HANDS_ON: "hands-on workshops",
}


def conflict_message(pref: str, conflicting: list[InterestCode]) -> str:
    """충돌 되묻기 문구(영어, 사용자-facing). 어느 쪽을 우선할지 사용자가 고르게 한다."""
    things = ", ".join(_INTEREST_LABEL.get(i, i.value) for i in conflicting)
    other = "outdoor" if pref == "indoor" else "indoor"
    return (
        f"You asked for {pref} spots, but {things} are mostly {other}. "
        f"Would you like {pref} options only, the {other} sights you mentioned, or a mix?"
    )


def conflict_notice(pref: str, conflicting: list[InterestCode]) -> str:
    """충돌 투명 안내(서술형) — 되묻지 않는 폼/즉시추천 경로용(Option 1).

    되묻기(conflict_message)와 달리 '이렇게 처리했다'를 알린다 — 조용히 한쪽을 버리지 않고
    왜 이런 결과인지 투명하게. 강등(A)·제외(B) 어느 쪽이든 맞는 중립 문구.
    """
    things = ", ".join(_INTEREST_LABEL.get(i, i.value) for i in conflicting)
    other = "outdoor" if pref == "indoor" else "indoor"
    return (
        f"You asked for {pref}, but {things} are mostly {other} — "
        f"results favor your {pref} preference."
    )
