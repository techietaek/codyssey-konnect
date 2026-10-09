"""결정론 실내/외 감지(domain/text_signals) 유닛테스트 — 부정·모호 처리 포함."""

from __future__ import annotations

from app.domain.text_signals import detect_indoor_outdoor


def test_plain_indoor_outdoor():
    assert detect_indoor_outdoor("indoor culture route") == ("indoor", False)
    assert detect_indoor_outdoor("something outdoors near me") == ("outdoor", False)


def test_strict_phrases():
    assert detect_indoor_outdoor("indoor only please") == ("indoor", True)
    assert detect_indoor_outdoor("strictly outdoor") == ("outdoor", True)


def test_negation_flips_preference():
    # "no outdoor" / "nothing outdoors" 는 실내(strict) — 키워드 'outdoor' 에 속지 않는다.
    assert detect_indoor_outdoor("no outdoor stuff, too hot") == ("indoor", True)
    assert detect_indoor_outdoor("nothing indoors, I want fresh air") == (
        "outdoor",
        True,
    )


def test_ambiguous_returns_none():
    assert detect_indoor_outdoor("some indoor and some outdoor is fine") == (
        None,
        False,
    )


def test_none_when_absent_or_empty():
    assert detect_indoor_outdoor("palaces and museums") == (None, False)
    assert detect_indoor_outdoor(None) == (None, False)
    assert detect_indoor_outdoor("") == (None, False)
