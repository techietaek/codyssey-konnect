"""AI 분류 근거 키워드 테스트 (표시 전용, 신뢰: 산정된 분류만 노출 + 요청 매칭 플래그)."""

from __future__ import annotations

from app.domain.signals import classification_signals
from app.models.recommend import (
    Candidate,
    ExperienceType,
    InterestCode,
    ParsedConditions,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
)


def _cand(etype, price_status=PriceStatus.UNKNOWN):
    return Candidate(
        id="x",
        title="X",
        type=etype,
        status=ResultStatus.FITS,
        price=PriceInfo(
            status=price_status, display="", provenance=Provenance.CONFIRMED
        ),
    )


def _labels(signals):
    return [s.label for s in signals]


def _matched(signals):
    return {s.label for s in signals if s.matched}


def test_exhibition_indoor_heuristic():
    # 전시 유형 → exhibition·art + 유형 휴리스틱 indoor(verdict 없음).
    labels = _labels(classification_signals(_cand(ExperienceType.EXHIBITION)))
    assert labels[0] == "exhibition"
    assert "art" in labels
    assert "indoor" in labels


def test_llm_verdict_overrides_heuristic():
    labels = _labels(
        classification_signals(_cand(ExperienceType.EXHIBITION), io_verdict="outdoor")
    )
    assert "outdoor" in labels
    assert "indoor" not in labels


def test_historic_visit_signals():
    labels = _labels(classification_signals(_cand(ExperienceType.HISTORIC_VISIT)))
    assert "historic site" in labels
    assert "palace & historic" in labels
    assert "traditional" in labels
    assert "outdoor" in labels  # 유형 휴리스틱


def test_price_free_paid():
    assert "free" in _labels(
        classification_signals(_cand(ExperienceType.EXHIBITION, PriceStatus.FREE))
    )
    assert "paid" in _labels(
        classification_signals(_cand(ExperienceType.EXHIBITION, PriceStatus.PAID))
    )
    assert "free" not in _labels(
        classification_signals(_cand(ExperienceType.EXHIBITION, PriceStatus.UNKNOWN))
    )


def test_dedup_and_cap():
    sig = classification_signals(_cand(ExperienceType.PERFORMANCE))
    assert _labels(sig).count("performance") == 1
    assert len(sig) <= 5


def test_default_type_no_fabricated_type_keyword():
    assert classification_signals(_cand(ExperienceType.DEFAULT)) == []


def test_signals_are_english_only():
    for etype in ExperienceType:
        for s in classification_signals(_cand(etype, PriceStatus.FREE)):
            assert all(ord(ch) < 128 for ch in s.label), s.label


# ── matched 플래그 (사용자 요청 일치 → 녹색) ──
def test_no_cond_nothing_matched():
    sig = classification_signals(_cand(ExperienceType.EXHIBITION, PriceStatus.FREE))
    assert _matched(sig) == set()  # 요청 없음 → 전부 기본(흰색)


def test_interest_match_marks_type_and_interest():
    cond = ParsedConditions(interests=[InterestCode.ART_EXHIBITIONS])
    sig = classification_signals(_cand(ExperienceType.EXHIBITION), cond)
    m = _matched(sig)
    assert "exhibition" in m  # 유형이 요청 관심사를 충족
    assert "art" in m  # 관심사 카테고리 직접 일치
    assert "indoor" not in m  # 실내외는 요청 안 함


def test_indoor_request_marks_indoor():
    cond = ParsedConditions(indoor_outdoor="indoor")
    sig = classification_signals(_cand(ExperienceType.EXHIBITION), cond)
    assert "indoor" in _matched(sig)


def test_outdoor_request_does_not_match_indoor_place():
    cond = ParsedConditions(indoor_outdoor="outdoor")
    sig = classification_signals(_cand(ExperienceType.EXHIBITION), cond)
    assert "indoor" not in _matched(sig)  # 장소는 indoor, 요청은 outdoor → 불일치


def test_free_only_marks_free():
    cond = ParsedConditions(free_only=True)
    sig = classification_signals(_cand(ExperienceType.EXHIBITION, PriceStatus.FREE), cond)
    assert "free" in _matched(sig)
