"""문화경험 큐레이션 테스트 (PRD §6.4).

실관측 카테고리 기반: 역사·문화시설·축제는 포함, 의료관광·관광거리·음식거리는 제외.
"""

from __future__ import annotations

from app.domain.curation import is_cultural_experience


def _it(cat1="A02", cat3=""):
    return {"cat1": cat1, "cat3": cat3}


def test_history_included():
    # Myeongdong Cathedral, Bosingak 등
    assert is_cultural_experience(_it(cat3="A02010900")) is True


def test_cultural_facility_included():
    # 박물관·미술관 (문화시설)
    assert is_cultural_experience(_it(cat3="A02060300")) is True


def test_folk_museum_miscategorized_A0204_still_included():
    # 국립민속박물관 어린이박물관이 A0204로 오분류되어도 blacklist라 통과
    assert is_cultural_experience(_it(cat3="A02040800")) is True


def test_medical_tourism_excluded():
    assert is_cultural_experience(_it(cat3="A02020500")) is False


def test_tourist_street_excluded():
    # 명동(지역)·관광안내소·케이블카 = A02030400
    assert is_cultural_experience(_it(cat3="A02030400")) is False


def test_food_alley_excluded():
    assert is_cultural_experience(_it(cat3="A02030600")) is False


def test_non_a02_excluded():
    # 자연(A01)·쇼핑(A04)·음식(A05) 등
    assert is_cultural_experience(_it(cat1="A04", cat3="A04010100")) is False


def test_missing_category_excluded():
    assert is_cultural_experience({}) is False
