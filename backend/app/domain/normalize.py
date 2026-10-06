"""TourAPI 응답 → 정규화 (단일 지점, PRD §6.2).

신뢰 불변식(CLAUDE §6):
- 요금 필드가 비었으면 `free` 가 아니라 `unknown` 으로 둔다(추정 금지).
- 운영시간이 없으면 `미확인`. 임의 숫자/시간 생성 금지.
- 좌표는 한국 범위로 range 검증 후 이상치 drop.
- 예약·참여는 TourAPI로 확인 불가 → 표기하지 않는다(‘예약 불필요’로 매핑 금지).

판정(3상태·시간충돌)은 여기서 하지 않는다 — A3(domain/constraints)에서. A2는
모두 `check_needed` 로 두고 미확인 flag만 표기한다(판정 전 상태).
"""

from __future__ import annotations

import re
from typing import Any

from app.models.recommend import (
    Candidate,
    ExperienceType,
    OfficialLink,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
    TimeInfo,
    UnconfirmedFlag,
)

# contenttypeid(EngService2) → 유형 키 (DESIGN §3.4). 미상은 default.
_TYPE_MAP = {
    "76": ExperienceType.HISTORIC_VISIT,  # Tourist attractions (궁·역사 등)
    "78": ExperienceType.EXHIBITION,  # Cultural facilities (박물관·미술관)
    "85": ExperienceType.FESTIVAL_EVENT,  # Festivals/Performances/Events
}

# 좌표 한국 범위 (이상치 drop)
_LAT_RANGE = (33.0, 39.0)
_LNG_RANGE = (124.0, 132.0)

# 운영시간/요금은 타입별로 필드명이 다름 → 존재하는 첫 값을 쓴다.
_HOURS_KEYS = [
    "usetime",
    "usetimeculture",
    "usetimefestival",
    "opentime",
    "usetimeleports",
]
_FEE_KEYS = ["usefee", "usefeeculture", "usetimefestival2"]


def _clean_title(title: str | None) -> str:
    """'English (한글…)' 끝의 한글 괄호 설명 제거 → 영문 우선(중첩 괄호 포함)."""
    t = title or ""
    return re.sub(r"\s*\(.*[가-힣].*\)\s*$", "", t).strip()


def _strip_html(s: str | None) -> str:
    return (
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or ""))
        .replace("&nbsp;", " ")
        .strip()
    )


def _first(d: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _href(html: str | None) -> str:
    m = re.search(r'href="([^"]+)"', html or "")
    return m.group(1) if m else ""


def normalize_price(raw: str) -> PriceInfo:
    """요금 문자열 → 정규화. 빈값·모호값은 unknown(무료 추정 금지)."""
    text = _strip_html(raw)
    if not text:
        return PriceInfo(
            status=PriceStatus.UNKNOWN,
            display="Price needs checking",
            raw=None,
            provenance=Provenance.UNCONFIRMED,
        )
    low = text.lower()
    has_num = bool(re.search(r"\d", text))
    mentions_free = "free" in low or "무료" in text
    mentions_paid = "paid" in low or "유료" in text or "charge" in low

    if mentions_free and not has_num:
        return PriceInfo(
            status=PriceStatus.FREE,
            display="Free",
            raw=text,
            provenance=Provenance.CONFIRMED,
        )
    if mentions_free and has_num:
        # 일부 무료·일부 유료 → 애매(대표가격으로 쓰지 않음)
        return PriceInfo(
            status=PriceStatus.PARTIAL_OR_AMBIGUOUS,
            display=text[:60],
            raw=text,
            provenance=Provenance.CONFIRMED,
        )
    if has_num:
        return PriceInfo(
            status=PriceStatus.PAID,
            display=text[:60],
            raw=text,
            provenance=Provenance.CONFIRMED,
        )
    if mentions_paid:
        # 유료 확인·금액 미상
        return PriceInfo(
            status=PriceStatus.UNKNOWN,
            display="Paid · amount needs checking",
            raw=text,
            provenance=Provenance.UNCONFIRMED,
        )
    # 모호/자유기술 → 미확인
    return PriceInfo(
        status=PriceStatus.UNKNOWN,
        display="Price needs checking",
        raw=text,
        provenance=Provenance.UNCONFIRMED,
    )


def normalize_hours(intro: dict[str, Any]) -> TimeInfo | None:
    """운영시간 → 확인된 표시값. 없으면 None(미확인)."""
    raw = _first(intro, _HOURS_KEYS)
    if not raw:
        return None
    return TimeInfo(display=_strip_html(raw)[:80], provenance=Provenance.CONFIRMED)


def _valid_coords(item: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lat = float(item.get("mapy"))
        lng = float(item.get("mapx"))
    except (TypeError, ValueError):
        return None
    if _LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LNG_RANGE[0] <= lng <= _LNG_RANGE[1]:
        return lat, lng
    return None


def normalize_candidate(
    item: dict[str, Any], intro: dict[str, Any], common: dict[str, Any]
) -> Candidate | None:
    """list item + 상세(intro/common) → Candidate. 이상치는 None(drop)."""
    coords = _valid_coords(item)
    if coords is None:
        return None
    lat, lng = coords
    title = _clean_title(item.get("title"))
    if not title:
        return None

    etype = _TYPE_MAP.get(str(item.get("contenttypeid")), ExperienceType.DEFAULT)
    price = normalize_price(_first(intro, _FEE_KEYS))
    time_info = normalize_hours(intro)

    flags: list[UnconfirmedFlag] = []
    if price.status == PriceStatus.UNKNOWN:
        flags.append(UnconfirmedFlag(text="Price needs checking"))
    if time_info is None:
        flags.append(UnconfirmedFlag(text="Hours need checking"))

    links: list[OfficialLink] = []
    homepage = _href(common.get("homepage", ""))
    if homepage:
        links.append(OfficialLink(label="View official details", url=homepage))

    image = item.get("firstimage") or None  # 공식 이미지만, 없으면 None(제외 안 함)

    return Candidate(
        id=f"tour-{item.get('contentid')}",
        title=title,
        type=etype,
        status=ResultStatus.CHECK_NEEDED,  # 판정 전(A3에서 3상태 산정)
        reasons=[],  # Reason은 A5(LLM)
        time=time_info,
        price=price,
        movement=None,  # 도보 거리/시간은 A4(Tmap)
        flags=flags,
        image_url=image,
        official_links=links,
        lat=lat,
        lng=lng,
    )
