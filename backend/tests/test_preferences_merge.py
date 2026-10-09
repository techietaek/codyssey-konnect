"""저장 선호 병합 테스트 (Phase 2 L2 · FR-L4·L5).

핵심 불변식: Request(note) 우선 — 저장 선호는 note 침묵 시에만 관심사를 Soft 채움,
이번 요청 기피 관심사는 저장 선호로도 넣지 않는다. 원본 불변.
"""

from __future__ import annotations

from app.domain.preferences_merge import (
    merge_saved_interests,
    merge_saved_open_preferences,
    merge_saved_walks,
)
from app.domain.ranking import display_sort_key
from app.models.recommend import (
    Candidate,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    ResultStatus,
)

ART = InterestCode.ART_EXHIBITIONS
TRAD = InterestCode.TRADITIONAL
PALACE = InterestCode.PALACES_HISTORIC


def test_note_interests_win_over_saved():
    """note 가 관심사를 말했으면 저장 선호는 적용하지 않는다(과개인화 방지)."""
    cond = ParsedConditions(interests=[ART])
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == [ART]


def test_saved_fills_when_note_silent():
    """note 가 관심사를 말하지 않으면 저장 관심사를 Soft 신호로 채운다."""
    cond = ParsedConditions()
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == [TRAD, PALACE]


def test_avoided_this_request_not_refilled():
    """이번 요청에서 기피한 관심사는 저장 선호로도 다시 넣지 않는다."""
    cond = ParsedConditions(avoid_interests=[TRAD])
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == [PALACE]


def test_no_saved_is_noop():
    cond = ParsedConditions()
    assert merge_saved_interests(cond, None).interests == []
    assert merge_saved_interests(cond, []).interests == []


def test_all_saved_avoided_leaves_empty():
    """저장 관심사가 전부 이번 기피면 채우지 않는다(빈 상태 유지)."""
    cond = ParsedConditions(avoid_interests=[TRAD, PALACE])
    out = merge_saved_interests(cond, [TRAD, PALACE])
    assert out.interests == []


def test_original_not_mutated():
    cond = ParsedConditions()
    merge_saved_interests(cond, [TRAD])
    assert cond.interests == []  # 원본 불변


# ── 저장 개방형 선호(P-09) 병합 ──
def test_saved_open_prefs_fill_when_note_silent():
    cond = ParsedConditions()
    out = merge_saved_open_preferences(cond, ["quiet", "photogenic"])
    assert out.open_preferences == ["quiet", "photogenic"]


def test_note_open_prefs_win_over_saved():
    # note 가 이미 개방형 선호를 말했으면 저장 선호는 적용 안 함(Request 우선).
    cond = ParsedConditions(open_preferences=["romantic"])
    out = merge_saved_open_preferences(cond, ["quiet"])
    assert out.open_preferences == ["romantic"]


def test_saved_open_prefs_noop_and_immutable():
    cond = ParsedConditions()
    assert merge_saved_open_preferences(cond, None).open_preferences == []
    assert merge_saved_open_preferences(cond, []).open_preferences == []
    merge_saved_open_preferences(cond, ["quiet"])
    assert cond.open_preferences == []  # 원본 불변


# ── 걷기 선호 병합 (Request 우선, 3-state) ──
def test_prompt_long_walk_overrides_saved_shorter():
    # 저장=shorter(true)인데 프롬프트가 'long walk OK'(false) → 프롬프트 최우선.
    cond = ParsedConditions(prefer_shorter_walks=False)
    out = merge_saved_walks(cond, True)
    assert out.prefer_shorter_walks is False


def test_prompt_shorter_kept():
    cond = ParsedConditions(prefer_shorter_walks=True)
    assert merge_saved_walks(cond, None).prefer_shorter_walks is True


def test_saved_fills_when_note_silent_walks():
    cond = ParsedConditions()  # None = 언급 안 함
    assert merge_saved_walks(cond, True).prefer_shorter_walks is True
    assert merge_saved_walks(ParsedConditions(), None).prefer_shorter_walks is None


def test_walks_original_not_mutated():
    cond = ParsedConditions()
    merge_saved_walks(cond, True)
    assert cond.prefer_shorter_walks is None


def _cand(etype, status=ResultStatus.FITS, title="x"):
    return Candidate(
        id=title,
        title=title,
        type=etype,
        status=status,
        reasons=[],
        flags=[],
        official_links=[],
    )


def test_saved_interest_bumps_order_when_note_silent():
    """통합 seam: note 침묵 시 저장 관심사가 같은 등급 내 표시 순서를 올린다(제외 아님).

    merge_saved_interests → display_sort_key 의 실제 연결을 검증한다. 저장=ART 면
    같은 FITS 등급의 전시 후보가 역사 후보보다 앞선다(Soft tiebreak, A안).
    """
    cond = merge_saved_interests(ParsedConditions(), [ART])
    art = _cand(ExperienceType.EXHIBITION, title="art")
    hist = _cand(ExperienceType.HISTORIC_VISIT, title="hist")
    ordered = sorted([hist, art], key=lambda c: display_sort_key(c, cond))
    assert [c.title for c in ordered] == ["art", "hist"]


def test_saved_interest_is_primary_b_plan():
    """B안(관심사 우선, Product 2026-10-07): 저장 관심사면 check_needed 라도 중립 fits
    앞으로. 사실은 안 바뀐다 — 각 카드 상태 배지는 그대로(fits/check). 제외도 아님."""
    cond = merge_saved_interests(ParsedConditions(), [ART])
    art_check = _cand(ExperienceType.EXHIBITION, ResultStatus.CHECK_NEEDED, "art_chk")
    hist_fit = _cand(ExperienceType.HISTORIC_VISIT, ResultStatus.FITS, "hist_fit")
    ordered = sorted([art_check, hist_fit], key=lambda c: display_sort_key(c, cond))
    assert [c.title for c in ordered] == ["art_chk", "hist_fit"]
