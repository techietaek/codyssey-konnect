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


def type_from_contenttype(contenttypeid: str | None) -> ExperienceType:
    """contenttypeid → 유형(상세조회 전 선발용). 미상은 default."""
    return _TYPE_MAP.get(str(contenttypeid), ExperienceType.DEFAULT)


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

# detailInfo2(반복 행)에서 요금·운영시간을 보강할 때 매칭할 infoname 키워드.
# detailIntro2 의 usefee/usetime 이 빈 경우에만 fallback 으로 쓴다(공식 데이터).
_INFO_FEE_NAMES = ("admission", "fee", "요금", "입장")
_INFO_HOURS_NAMES = (
    "operating hour",
    "hours of",
    "use time",
    "business hour",
    "운영시간",
    "이용시간",
    "관람시간",
)


def _info_value(info_rows: list[dict[str, Any]], name_keywords: tuple[str, ...]) -> str:
    """infoname 이 키워드에 매칭되는 첫 행의 infotext(정리본). 없으면 ''."""
    for row in info_rows:
        name = str(row.get("infoname") or "").lower()
        if any(k in name for k in name_keywords):
            text = _strip_html(row.get("infotext"))
            if text:
                return text
    return ""


def enrich_intro(
    intro: dict[str, Any], info_rows: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """detailIntro2 에 요금·운영시간이 비면 detailInfo2 행에서 보강한 intro 사본을 반환.
    공식 TourAPI 데이터만 사용 — 추정/생성 아님. 값이 이미 있으면 덮어쓰지 않는다."""
    if not info_rows:
        return intro
    out = dict(intro)
    if not _first(out, _FEE_KEYS):
        fee = _info_value(info_rows, _INFO_FEE_NAMES)
        if fee:
            out["usefee"] = fee
    if not _first(out, _HOURS_KEYS):
        hours = _info_value(info_rows, _INFO_HOURS_NAMES)
        if hours:
            out["usetime"] = hours
    return out


# 한글(완성형·자모·호환자모) 문자 클래스. 표시 문자열에서 한글을 정확히 제거한다.
_HANGUL = r"가-힣ᄀ-ᇿ㄰-㆏ꥠ-꥿ힰ-퟿"
_HANGUL_RE = re.compile(f"[{_HANGUL}]")
# 한글이 든 괄호 묶음(소/대/중/꺾쇠/모서리). 소괄호는 1단계 중첩까지 균형 매칭
# ('동대문디자인플라자 (DDP)' 같은 내부 영문 괄호 포함 통째 제거), 나머지는 비탐욕 매칭.
_BRACKET_PATS = (
    re.compile(r"\s*\[[^\[\]]*\]"),
    re.compile(r"\s*\((?:[^()]|\([^()]*\))*\)"),
    re.compile(r"\s*\{[^{}]*\}"),
    re.compile(r"\s*<[^<>]*>"),
    re.compile(r"\s*「[^」]*」"),
    re.compile(r"\s*『[^』]*』"),
)
_HANGUL_RUN_RE = re.compile(f"[{_HANGUL}]+(?:[\\s·]+[{_HANGUL}]+)*")
# 영문 '이름'이 남았는지 — 숫자·기호만으론 이름이 못 되므로 ASCII 글자 기준으로 본다.
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")


def english_display(text: str | None) -> str:
    """표시 문자열에서 한글을 정확히 제거해 영문 우선 표기로 만든다(정규식, 생성 아님).

    예: 'Alive Museum (Insa-dong Branch) [박물관은 살아있다(인사동점)]'
        → 'Alive Museum (Insa-dong Branch)'.
    1) 한글이 든 괄호 묶음 제거(영문만 든 괄호는 보존), 2) 남은 한글 런 제거,
    3) 빈 괄호·중복 공백·양끝 구분자 정리. 결과에 **영문 글자(A-Z)** 가 남지 않으면
    (한글 이름 + 연도 숫자만 남는 '2026' 같은 경우 포함) 원문을 그대로 유지한다 — 이름을
    숫자·빈칸으로 지워버리지 않는다(사용자 요청: 적절히 지울 수 없으면 한글 그대로).
    """
    t = text or ""
    # 1) 한글 포함 괄호 묶음 제거(2회 반복 — 중첩 잔여 대응). 영문만 든 괄호는 유지.
    for _ in range(2):
        for pat in _BRACKET_PATS:
            t = pat.sub(lambda m: "" if _HANGUL_RE.search(m.group()) else m.group(), t)
    # 2) 괄호 밖에 남은 한글 런 제거.
    t = _HANGUL_RUN_RE.sub(" ", t)
    # 3) 정리: 빈 괄호·중복 공백·괄호 안쪽 공백·양끝 구분자.
    t = re.sub(r"[\(\[\{<「『]\s*[\)\]\}>」』]", "", t)
    t = re.sub(r"\s+([)\]\}>」』])", r"\1", t)
    t = re.sub(r"([(\[\{<「『])\s+", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" \t-·,/|")
    t = t.strip()
    # 영문 이름이 남지 않으면(한글 제목·숫자만 남는 경우 포함) 원문 유지(이름을 지우지 않음).
    return t if _LATIN_LETTER_RE.search(t) else (text or "").strip()


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


# 공식 권장 방문시간 필드(문화시설 spendtime·행사 spendtimefestival). 있을 때만 사용.
_SPEND_KEYS = ["spendtime", "spendtimefestival"]


def parse_duration_min(text: str | None) -> int | None:
    """'180 minutes'·'1시간 30분'·'about 2 hours' → 분. 파싱 불가/빈값은 None(추정 금지)."""
    t = _strip_html(text).lower()
    if not t:
        return None
    total = 0
    found = False
    for h in re.findall(r"(\d+)\s*(?:hours?|hrs?|시간)", t):
        total += int(h) * 60
        found = True
    for m in re.findall(r"(\d+)\s*(?:minutes?|mins?|분)", t):
        total += int(m)
        found = True
    return total if found and total > 0 else None


def official_visit_minutes(intro: dict[str, Any]) -> int | None:
    """공식 권장 방문 소요시간(분). spendtime/spendtimefestival 있을 때만, 없으면 None."""
    return parse_duration_min(_first(intro, _SPEND_KEYS))


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


# ── 서울문화포털 문화행사(culturalEventInfo) 정규화 ─────────────────────────────
# CODENAME(분류) → 유형. 미상/일반은 festival_event(행사 포털 기본).
_SEOUL_TYPE_KEYWORDS: list[tuple[tuple[str, ...], ExperienceType]] = [
    (("전시", "미술"), ExperienceType.EXHIBITION),
    (
        ("공연", "콘서트", "연극", "뮤지컬", "클래식", "무용", "국악", "오페라"),
        ExperienceType.PERFORMANCE,
    ),
    (("교육", "체험"), ExperienceType.HANDS_ON),
    (("축제", "행사"), ExperienceType.FESTIVAL_EVENT),
]


def _seoul_type(codename: str | None) -> ExperienceType:
    name = str(codename or "")
    for keywords, etype in _SEOUL_TYPE_KEYWORDS:
        if any(k in name for k in keywords):
            return etype
    return ExperienceType.FESTIVAL_EVENT


def _seoul_yyyymmdd(s: Any) -> str:
    """'2024-05-01 00:00:00.0' / '2024-05-01' → '20240501'. 파싱 불가면 ''(추정 금지)."""
    digits = re.sub(r"\D", "", str(s or ""))[:8]
    return digits if len(digits) == 8 else ""


def _valid_seoul_coords(row: dict[str, Any]) -> tuple[float, float] | None:
    """LOT/LAT 두 값을 범위로 안전 할당(이 API 는 이름이 관례와 뒤바뀜).

    위도(33–39)·경도(124–132) 범위에 각각 들어맞는 값으로 (lat, lng) 재구성한다.
    두 역할이 모두 채워질 때만 유효. 아니면 None(drop — 지도 핀 불가).
    """
    vals: list[float] = []
    for key in ("LOT", "LAT"):
        try:
            vals.append(float(str(row.get(key) or "").strip()))
        except (TypeError, ValueError):
            continue
    lat = next((v for v in vals if _LAT_RANGE[0] <= v <= _LAT_RANGE[1]), None)
    lng = next((v for v in vals if _LNG_RANGE[0] <= v <= _LNG_RANGE[1]), None)
    if lat is None or lng is None:
        return None
    return lat, lng


def seoul_event_intro(row: dict[str, Any]) -> dict[str, Any]:
    """서울 행사 row → 기간 판정용 합성 intro(STRTDATE/END_DATE 만). 운영시간은 미제공.

    기존 결정론 판정(judge_event_period·judge_timing)을 소스 불문 그대로 재사용하기 위한
    어댑터. 시간값을 지어내지 않는다 — 날짜만 매핑(없으면 빈값 → 미확인 판정).
    """
    return {
        "eventstartdate": _seoul_yyyymmdd(row.get("STRTDATE")),
        "eventenddate": _seoul_yyyymmdd(row.get("END_DATE")),
    }


def _seoul_price_text(row: dict[str, Any]) -> str:
    """요금 텍스트: USE_FEE 우선, 없으면 IS_FREE('무료'/'유료')만 신호로.

    빈값을 free 로 매핑하지 않는다(불변식). IS_FREE='무료'는 공식 소스의 '확인된 무료'.
    """
    fee = str(row.get("USE_FEE") or "").strip()
    if fee:
        return fee
    is_free = str(row.get("IS_FREE") or "").strip()
    return is_free  # '무료'→FREE, '유료'→UNKNOWN(금액 미확인), ''→UNKNOWN


def normalize_seoul_event(row: dict[str, Any]) -> Candidate | None:
    """서울문화포털 행사 row → Candidate. 좌표 이상치는 None(drop).

    제목은 english_display 로 한글 제거(표시 영문화). 단 영문 이름이 남지 않으면(한글
    축제명 등) 원문 한글을 그대로 유지한다(이름을 지우지 않음). 출처 배지 source='seoul'.
    """
    coords = _valid_seoul_coords(row)
    if coords is None:
        return None
    lat, lng = coords
    title = english_display(row.get("TITLE"))
    if not title:
        return None

    price = normalize_price(_seoul_price_text(row))
    # 행사는 '그날 안의 운영시간'이 구조화돼 있지 않다 → 미확인(시간 지어내지 않음).
    time_info = None

    flags: list[UnconfirmedFlag] = []
    if price.status == PriceStatus.UNKNOWN:
        flags.append(UnconfirmedFlag(text="Price needs checking"))
    flags.append(UnconfirmedFlag(text="Hours need checking"))

    links: list[OfficialLink] = []
    link = str(row.get("ORG_LINK") or row.get("HMPG_ADDR") or "").strip()
    if link.startswith("http"):
        links.append(OfficialLink(label="View official details", url=link))

    image = str(row.get("MAIN_IMG") or "").strip() or None

    # 안정적 id: 좌표 없는 소스라 TITLE+시작일로 합성(중복제거·재조회 일관성).
    uid = f"{title}|{_seoul_yyyymmdd(row.get('STRTDATE'))}"

    return Candidate(
        id=f"seoul-{abs(hash(uid)) % (10**10)}",
        title=title,
        source="seoul",
        type=_seoul_type(row.get("CODENAME")),
        status=ResultStatus.CHECK_NEEDED,  # 판정 전(orchestrator 에서 3상태 산정)
        reasons=[],
        time=time_info,
        price=price,
        movement=None,
        flags=flags,
        image_url=image,
        official_links=links,
        lat=lat,
        lng=lng,
    )


def normalize_candidate(
    item: dict[str, Any], intro: dict[str, Any], common: dict[str, Any]
) -> Candidate | None:
    """list item + 상세(intro/common) → Candidate. 이상치는 None(drop)."""
    coords = _valid_coords(item)
    if coords is None:
        return None
    lat, lng = coords
    title = english_display(item.get("title"))
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
        visit_minutes=official_visit_minutes(intro),  # 공식 권장 방문시간(있을 때만)
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
