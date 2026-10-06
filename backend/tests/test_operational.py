"""영업 상태(폐업/임시휴업) Hard 제외 판정 테스트 (PRD §6.7 예외).

음성 신호 전용: 폐업 확인 + 좌표 근접일 때만 제외. 미확인·불일치·결측은
제외하지 않는다(오탈락 방지).
"""

from __future__ import annotations

from app.domain.operational import PresenceVerdict, judge_presence

# 후보 좌표 (Alive Museum 인사동점 실측 근방)
_LAT, _LNG = 37.5718843, 126.9872034


def _place(status, lat=_LAT, lng=_LNG):
    return {"businessStatus": status, "location": {"latitude": lat, "longitude": lng}}


def test_permanently_closed_nearby_excluded():
    v = judge_presence(_place("CLOSED_PERMANENTLY"), _LAT, _LNG)
    assert v is PresenceVerdict.CLOSED_PERMANENTLY


def test_temporarily_closed_nearby_excluded():
    v = judge_presence(_place("CLOSED_TEMPORARILY"), _LAT, _LNG)
    assert v is PresenceVerdict.CLOSED_TEMPORARILY


def test_operational_not_excluded():
    v = judge_presence(_place("OPERATIONAL"), _LAT, _LNG)
    assert v is PresenceVerdict.OPERATIONAL


def test_no_places_result_not_excluded():
    # 보조 소스 미확인 → 제외하지 않는다(긍정 생성 아님, 오탈락 방지)
    assert judge_presence(None, _LAT, _LNG) is PresenceVerdict.OPERATIONAL


def test_closed_but_far_coords_not_excluded():
    # Places 가 폐업이라 해도 좌표가 멀면(다른 장소일 수 있음) 제외하지 않는다
    far = _place("CLOSED_PERMANENTLY", lat=37.5800, lng=126.9950)
    assert judge_presence(far, _LAT, _LNG) is PresenceVerdict.OPERATIONAL


def test_closed_but_missing_coords_not_excluded():
    # 좌표 결측 → 같은 장소인지 신뢰 불가 → 제외하지 않는다
    no_loc = {"businessStatus": "CLOSED_PERMANENTLY"}
    assert judge_presence(no_loc, _LAT, _LNG) is PresenceVerdict.OPERATIONAL
    assert judge_presence(_place("CLOSED_PERMANENTLY"), None, None) is (
        PresenceVerdict.OPERATIONAL
    )


def test_unknown_status_not_excluded():
    assert judge_presence(_place(""), _LAT, _LNG) is PresenceVerdict.OPERATIONAL
