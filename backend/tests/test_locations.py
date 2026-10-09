"""지명 감지(domain/locations.detect_location_in_text) 유닛테스트 — 결정론."""

from __future__ import annotations

from app.domain.locations import detect_location_in_text


def test_detects_known_landmark_in_free_text():
    loc = detect_location_in_text("Plan a route, I am at Myeongdong please")
    assert loc is not None
    assert abs(loc.lat - 37.5637) < 0.01 and abs(loc.lng - 126.9850) < 0.01


def test_case_insensitive():
    assert detect_location_in_text("i'm near GYEONGBOKGUNG now") is not None


def test_unknown_location_returns_none():
    # 테이블에 없는 지명은 좌표를 지어내지 않고 None(앱 컨텍스트로 폴백).
    assert detect_location_in_text("I am at some random alley in Busan") is None


def test_empty_returns_none():
    assert detect_location_in_text(None) is None
    assert detect_location_in_text("") is None
