"""저장된 장기 선호 → 현재 요청 조건 병합 (Phase 2 L2 · FR-L4·L5).

불변식(CLAUDE §6):
- **Request > Trip > Preference.** note(현재 요청)가 말한 관심사는 저장 선호가
  덮어쓰지 않는다. 저장 관심사는 note 가 **아무 관심사도 말하지 않았을 때만**
  Soft 신호로 채운다(후보 집합을 바꾸지 않는 tiebreak — domain/ranking).
- 이번 요청에서 **기피(avoid)한 관심사는 저장 선호로도 다시 넣지 않는다.**
- **걷기 선호는 여기서 다루지 않는다** — ParsedConditions 는 'note 가 말한 것'만
  담는 스키마이고, 걷기 선호는 수치 상한으로 변환 금지(FR-L4). flag 전달·trace 는
  호출부(orchestrator)에서 별도로.
"""

from __future__ import annotations

from app.models.recommend import InterestCode, ParsedConditions


def merge_saved_interests(
    cond: ParsedConditions, saved_interests: list[InterestCode] | None
) -> ParsedConditions:
    """note 가 관심사를 말하지 않았을 때만 저장 관심사로 채운다(Request 우선).

    - note 에 관심사 있음 → 그대로(저장 선호 미적용, 과개인화 방지).
    - note 침묵 → 저장 관심사 중 이번 요청에서 기피하지 않은 것만 Soft 신호로.
    반환은 새 객체(원본 불변).
    """
    if cond.interests:
        return cond
    if not saved_interests:
        return cond
    avoid = set(cond.avoid_interests)
    filled = [i for i in saved_interests if i not in avoid]
    if not filled:
        return cond
    return cond.model_copy(update={"interests": filled})
