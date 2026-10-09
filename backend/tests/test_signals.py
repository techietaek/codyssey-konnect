"""AI 분류 근거 키워드 테스트 (표시 전용, 신뢰: 산정된 분류만 노출)."""

from __future__ import annotations

from app.domain.signals import classification_signals
from app.models.recommend import (
    Candidate,
    ExperienceType,
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


def test_exhibition_indoor_heuristic():
    # 전시 유형 → exhibition·art + 유형 휴리스틱 indoor(verdict 없음).
    sig = classification_signals(_cand(ExperienceType.EXHIBITION))
    assert sig[0] == "exhibition"
    assert "art" in sig
    assert "indoor" in sig


def test_llm_verdict_overrides_heuristic():
    # LLM verdict(outdoor)가 유형 휴리스틱(indoor)보다 우선.
    sig = classification_signals(
        _cand(ExperienceType.EXHIBITION), io_verdict="outdoor"
    )
    assert "outdoor" in sig
    assert "indoor" not in sig


def test_historic_visit_signals():
    sig = classification_signals(_cand(ExperienceType.HISTORIC_VISIT))
    assert "historic site" in sig
    assert "palace & historic" in sig
    assert "traditional" in sig
    assert "outdoor" in sig  # 유형 휴리스틱


def test_price_free_paid():
    assert "free" in classification_signals(
        _cand(ExperienceType.EXHIBITION, PriceStatus.FREE)
    )
    assert "paid" in classification_signals(
        _cand(ExperienceType.EXHIBITION, PriceStatus.PAID)
    )
    # unknown 가격은 키워드 없음(지어내지 않음).
    assert "free" not in classification_signals(
        _cand(ExperienceType.EXHIBITION, PriceStatus.UNKNOWN)
    )


def test_dedup_and_cap():
    # performance 유형 + live_performances 관심사 → 'performance' 한 번만.
    sig = classification_signals(_cand(ExperienceType.PERFORMANCE))
    assert sig.count("performance") == 1
    assert len(sig) <= 5


def test_default_type_no_fabricated_type_keyword():
    sig = classification_signals(_cand(ExperienceType.DEFAULT))
    # default 는 유형 키워드·휴리스틱 실내외 없음 — 가격만(여기선 unknown → 빈 리스트).
    assert sig == []


def test_signals_are_english_only():
    for etype in ExperienceType:
        for kw in classification_signals(_cand(etype, PriceStatus.FREE)):
            assert all(ord(ch) < 128 for ch in kw), kw
