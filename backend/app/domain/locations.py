"""시작 좌표 해석 (A2).

우선순위: 요청에 실제 좌표(현재위치) > 대표 시작점(FR-A5) 하드코딩 좌표 > 도심 기본값.
임의 자유텍스트의 정밀 지오코딩은 이후 슬라이스(보조 소스)에서 보강한다.
좌표를 추정으로 지어내지 않되, MVP 우선 지역(서울 도심 문화권)에서 조회가
성립하도록 알려진 대표 좌표만 매핑한다.
"""

from __future__ import annotations

from app.models.recommend import StartLocation

# FR-A5 대표 시작점 5개 + 흔한 표기. 값은 공개된 랜드마크 좌표(lat, lng).
_QUICK_COORDS: dict[str, tuple[float, float]] = {
    "gyeongbokgung": (37.5796, 126.9770),
    "anguk": (37.5742, 126.9858),
    "insadong": (37.5740, 126.9850),
    "city hall": (37.5663, 126.9779),
    "deoksugung": (37.5658, 126.9751),
    "myeongdong": (37.5637, 126.9850),
    "ddp": (37.5663, 127.0090),
    "dongdaemun": (37.5663, 127.0090),
}

# 서울 도심 문화권 기본 중심(광화문/종로 근처). 라벨 매칭 실패 시 폴백.
_DEFAULT = (37.5700, 126.9830)


def resolve_start_coords(loc: StartLocation) -> tuple[float, float]:
    if loc.lat is not None and loc.lng is not None:
        return loc.lat, loc.lng
    key = (loc.label or "").strip().lower()
    for name, coords in _QUICK_COORDS.items():
        if name in key:
            return coords
    return _DEFAULT
