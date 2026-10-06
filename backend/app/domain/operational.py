"""영업 상태 판정 — 폐업/임시휴업 Hard 제외 (음성 신호 전용).

배경: TourAPI(공식 정본)는 레코드를 즉시 purge 하지 않아, 이미 **폐업**한 장소가
정상 운영시간·요금과 함께 그대로 내려올 수 있다. TourAPI 스키마엔 '폐업' 필드가
없어 domain/timing 의 결정론적 판정으로는 잡히지 않는다.

보완: Google Places (New) `businessStatus`(운영 사실)를 **음성 신호로만** 사용해,
'영구폐업/임시휴업'이 확인되면 Hard 제외한다. 긍정(이용 가능)으로는 쓰지 않는다
(CLAUDE §6: 미확인을 긍정으로 바꾸지 않는다). Places 미확인·불일치는 제외하지
않는다(오탈락 방지 — 잘못된 제외도 신뢰 위반).

PRD §6.7 예외: Places `businessStatus` 는 price_level·평점·리뷰 금지와 별개로,
폐업 확인(음성 신호)에 한해 Hard 제외 판정에 사용 허용.
"""

from __future__ import annotations

from enum import Enum
from math import asin, cos, radians, sin, sqrt
from typing import Any

# Places 결과가 '같은 장소'라고 볼 최대 좌표 오차(m). 초과 시 매칭 불신 → 제외 안 함.
_MATCH_RADIUS_M = 120.0

_CLOSED_STATUSES = ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY")


class PresenceVerdict(str, Enum):
    OPERATIONAL = "operational"  # 영업중 확인(또는 판단 근거 없음) — 제외 안 함
    CLOSED_PERMANENTLY = "closed_permanently"  # 영구폐업 — Hard 제외
    CLOSED_TEMPORARILY = "closed_temporarily"  # 임시휴업 — Hard 제외(지금 방문 불가)


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def judge_presence(
    place: dict[str, Any] | None,
    cand_lat: float | None,
    cand_lng: float | None,
) -> PresenceVerdict:
    """Places 결과(businessStatus+location)와 후보 좌표 → 영업상태 판정.

    제외는 (1) Places 가 폐업/임시휴업을 명시하고 (2) 좌표가 후보와 근접(같은 장소로
    신뢰)할 때만. 그 외(근거 없음·OPERATIONAL·좌표 불일치·좌표 결측)는 OPERATIONAL
    로 두어 제외하지 않는다.
    """
    if not place:
        return PresenceVerdict.OPERATIONAL
    status = str(place.get("businessStatus") or "").upper()
    if status not in _CLOSED_STATUSES:
        return PresenceVerdict.OPERATIONAL

    # 같은 장소인지 좌표로 교차확인 — 오탈락(엉뚱한 Places 매칭) 방지.
    loc = place.get("location") or {}
    plat, plng = loc.get("latitude"), loc.get("longitude")
    if cand_lat is None or cand_lng is None or plat is None or plng is None:
        return PresenceVerdict.OPERATIONAL  # 매칭 신뢰 불가 → 제외 안 함
    if _haversine_m(cand_lat, cand_lng, float(plat), float(plng)) > _MATCH_RADIUS_M:
        return PresenceVerdict.OPERATIONAL  # 다른 장소일 수 있음 → 제외 안 함

    return (
        PresenceVerdict.CLOSED_PERMANENTLY
        if status == "CLOSED_PERMANENTLY"
        else PresenceVerdict.CLOSED_TEMPORARILY
    )
