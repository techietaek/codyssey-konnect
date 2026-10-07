"""개방형 명시 배제 — 선별·0건-세이프 (옵션3, 결정론 코드).

LLM(agent/exclude_classifier)은 "어떤 후보가 배제 개념에 매칭되나"만 판단하고,
**무엇을 유지·제외·안내하느냐는 여기(코드)가 결정**한다(사실·가드레일은 코드 소유).

신뢰 경계(CLAUDE §6 · agent-architecture §3):
- 배제는 거리순 유효 후보에서 매칭분을 '제거'만 — 강제 채움 없음(남은 것만, 최대 N).
- **0건-세이프**: 배제가 유효 후보를 전부 비우면 배제를 적용하지 않고 유지 + 안내.
  (개인화가 '가능한 것'을 0건으로 만들지 않음 — 비면 가까운 대체를 투명하게 보여준다.)
"""

from __future__ import annotations


def select_with_exclusion(
    ids: list[str],
    exclude_ids: set[str],
    concepts: list[str],
    max_candidates: int,
) -> tuple[list[str], list[str], set[str]]:
    """거리순 id 리스트에서 배제분 제거 후 상위 N 선별.

    반환: (kept_ids, notices, applied) —
      kept_ids: 표시할 후보 id(거리순 유지, 최대 max_candidates),
      notices: 사용자-facing 안내(0건-세이프 시 1건),
      applied: 실제로 적용된 배제 id 집합(0건-세이프면 빈 집합).
    """
    remaining = [i for i in ids if i not in exclude_ids]
    notices: list[str] = []
    applied = set(exclude_ids)
    # 0건-세이프: 배제가 (있던) 유효 후보를 전부 비우면 배제하지 않고 유지 + 안내.
    # ids 자체가 비면 배제 탓이 아닌 '진짜 0건'이라 해당 안 됨(호출부가 별도 안내).
    if concepts and exclude_ids and ids and not remaining:
        remaining = list(ids)
        applied = set()
        phrase = ", ".join(concepts)
        notices.append(
            f"We couldn't find options that avoid {phrase} — showing the closest matches."
        )
    return remaining[:max_candidates], notices, applied
