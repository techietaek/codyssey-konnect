"""즉시 추천(A) 파이프라인.

structure(입력+note LLM 구조화) → fetch(공식 API) → judge(운영/휴무/예산) →
route(Tmap) → explain(Reason) → compose. 한 소스 실패가 전체 실패로 번지지 않게
부분 실패를 허용한다(CLAUDE §4.2). 판정·Reason은 코드로, LLM은 note 구조화만.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.agent.classify import classify_places
from app.agent.context import RequestContext
from app.agent.environment import get_environment
from app.agent.exclude_classifier import classify_excluded
from app.agent.hours_parser import parse_hours
from app.agent.note_parser import parse_note
from app.agent.semantic_rank import (
    build_intent_text,
    pool_item_text,
    semantic_similarities,
)
from app.core.exceptions import ExternalSourceError
from app.core.trace import Trace
from app.domain.budget import BudgetVerdict, judge_budget
from app.domain.curation import is_cultural_experience
from app.domain.dedup import dedup_cross_source
from app.domain.exclusion import match_excluded_places, select_with_exclusion
from app.domain.locations import resolve_start_coords
from app.domain.normalize import (
    _seoul_type,
    _strip_html,
    _valid_seoul_coords,
    enrich_intro,
    normalize_candidate,
    normalize_seoul_event,
    seoul_event_intro,
    type_from_contenttype,
)
from app.domain.operational import PresenceVerdict, judge_presence
from app.domain.preferences_merge import merge_saved_interests
from app.domain.ranking import display_sort_key, io_rank, type_preference_rank
from app.domain.reasons import select_reasons
from app.domain.route import haversine_m
from app.domain.status import resolve_status
from app.domain.timing import (
    EventPeriod,
    TimingVerdict,
    judge_event_period,
    judge_extracted_hours,
    judge_timing,
    operating_hours_text,
    should_retry_hours_with_llm,
)
from app.models.recommend import (
    Candidate,
    InterestCode,
    MovementInfo,
    ParsedConditions,
    Provenance,
    RecommendData,
    StartLocation,
)
from app.sources import gplaces, seoulculture, tmap, tourapi

# 문화경험 콘텐츠 타입(EngService2): 관광지·문화시설·축제/공연/행사.
# (식당·쇼핑·숙박 등은 제외 — PRD §6.4)
_CULTURAL_TYPES = (76, 78, 85)
_SEARCH_RADIUS_M = 1500
_MAX_CANDIDATES = 4
_ENRICH_POOL = 8  # 판정 후 Hard 제외분을 다음 후보로 대체하기 위한 보강 범위

# [P1] 적응형 반경 ladder — 결과가 희소할 때만 단계적으로 넓혀 재조회(§7 P1, L1/L4).
# 흔한 밀집 지역은 1단계(1500m)에서 바로 충족돼 확장이 트리거되지 않는다(지연 불변).
_RADIUS_LADDER = (1500, 3000, 5000)
_MIN_VIABLE = 2  # 유효 후보가 이 수 미만이면 '선택지 부족' → 반경 확대(강제 채움 아님)
_RADIUS_EXPANDED_NOTICE = (
    "Few options were nearby, so we widened the search area to find more."
)


async def _fetch_tour_pool(
    lat: float, lng: float, radius: int = _SEARCH_RADIUS_M
) -> tuple[list[dict], int]:
    """TourAPI 문화 타입별 목록 병렬 조회 → 병합·중복제거. (pool, 실패소스수)."""
    results = await asyncio.gather(
        *(tourapi.location_based_list(lat, lng, radius, t) for t in _CULTURAL_TYPES),
        return_exceptions=True,
    )
    ok_lists = [r for r in results if not isinstance(r, Exception)]
    failed = len(results) - len(ok_lists)
    if not ok_lists:
        raise ExternalSourceError("TourAPI unavailable for all cultural types")

    # 문화경험이 아닌 카테고리(의료관광·관광거리·안내소·음식거리 등)를 제외한다.
    # 판단은 domain/curation 으로 분리(PRD §6.4, 테스트 가능).
    merged: dict[str, dict] = {}
    for items in ok_lists:
        for it in items:
            cid = it.get("contentid")
            if cid and cid not in merged and is_cultural_experience(it):
                it["_src"] = "tour"
                it["_etype"] = type_from_contenttype(it.get("contenttypeid"))
                try:
                    it["_lat"] = float(it.get("mapy"))
                    it["_lng"] = float(it.get("mapx"))
                except (TypeError, ValueError):
                    it["_lat"] = it["_lng"] = None
                merged[cid] = it
    return list(merged.values()), failed


async def _fetch_seoul_pool(
    lat: float, lng: float, on_date: date, radius: int = _SEARCH_RADIUS_M
) -> list[dict]:
    """서울문화포털 '그날 열리는' 행사 조회 → 좌표 거리 후필터(반경 내)·거리 태깅.

    API 가 dist 를 주지 않아 좌표로 haversine 계산(domain/route)해 반경 밖은 제외한다.
    좌표 없는 행사는 지도 핀 불가 → drop(임의 좌표 생성 금지). 실패는 상위에서 graceful.
    """
    rows = await seoulculture.cultural_events(on_date)
    pool: list[dict] = []
    for row in rows:
        coords = _valid_seoul_coords(row)
        if coords is None:
            continue
        d = haversine_m(lat, lng, coords[0], coords[1])
        if d > radius:
            continue
        row["dist"] = d
        row["_src"] = "seoul"
        row["_etype"] = _seoul_type(row.get("CODENAME"))
        row["_lat"], row["_lng"] = coords
        pool.append(row)
    return pool


async def _fetch_pool(
    lat: float,
    lng: float,
    trace: Trace,
    on_date: date,
    radius: int = _SEARCH_RADIUS_M,
) -> list[dict]:
    """멀티소스(TourAPI + 서울문화포털) 병렬 조회 → 병합·거리순. 부분 실패 허용(§6.2).

    on_date 는 서울 행사 '그날 열림' 필터 기준(방문일, ctx.start_at.date()).
    radius 는 조회 반경(m) — P1 적응형 ladder 가 희소 결과 시 넓혀 호출한다.
    TourAPI 가 전부 실패하면 예외(기본 추천 성립 불가), 서울 소스 실패는 graceful 로 흡수.
    """
    tour_res, seoul_res = await asyncio.gather(
        _fetch_tour_pool(lat, lng, radius),
        _fetch_seoul_pool(lat, lng, on_date, radius),
        return_exceptions=True,
    )
    if isinstance(tour_res, Exception):
        raise tour_res
    tour_pool, tour_failed = tour_res

    if isinstance(seoul_res, Exception):
        seoul_pool: list[dict] = []
        seoul_ok = False
    else:
        seoul_pool = seoul_res
        seoul_ok = True

    def _dist(it: dict) -> float:
        try:
            return float(it.get("dist") or 1e12)
        except (TypeError, ValueError):
            return 1e12

    # [dedup] 같은 행사가 TourAPI 85·서울 양쪽에 중복될 수 있어 좌표근접 교차 제거(§6.2).
    merged, dup_removed = dedup_cross_source([*tour_pool, *seoul_pool])
    pool = sorted(merged, key=_dist)
    trace.step(
        "fetch",
        radius=radius,
        pool=len(pool),
        tour=len(tour_pool),
        seoul=len(seoul_pool),
        dup_removed=dup_removed,
        tour_sources_failed=tour_failed,
        seoul_ok=seoul_ok,
    )
    return pool


@dataclass
class SourceRecord:
    """정규화된 사실(Candidate) + 가용성 판정에 필요한 공식 입력 묶음.

    search(사실)와 check(가용성)를 분리하기 위한 단위(§6.2·§6.4). search 단계가 만들고
    check 단계가 소비한다. judge_intro 는 timing/event 판정용 공식 dict(tour=실제 intro,
    seoul=기간 합성). 사실은 요청(ctx)과 무관 — 여기엔 사용자 시간·선호를 담지 않는다.
    """

    candidate: Candidate
    source: str
    judge_intro: dict[str, Any]
    classify_text: str
    place: dict[str, Any] | None = None  # Places businessStatus (tour 폐업 신호용)
    check_event_period: bool = (
        False  # 날짜형(행사/공연·type85) 종료/미개막 Hard 판정 대상
    )
    check_presence: bool = False  # Places 폐업 신호 Hard 판정 대상(tour 전용)
    allow_llm_hours: bool = False  # 운영시간 UNCERTAIN→OPEN LLM 재추출 허용(tour 전용)


async def _fetch_and_normalize(item: dict) -> SourceRecord | None:
    """[search 사실] 상세 조회 → 공통 Candidate 정규화. 판정은 하지 않는다(요청 무관).

    소스별 분기: 서울 행사는 목록이 완성형(2차 조회 없음), TourAPI 는 detail 2차 조회.
    이상치(좌표/제목)는 None(drop). Hard 판정에 필요한 공식 입력은 SourceRecord 에 싣는다.
    """
    if item.get("_src") == "seoul":
        cand = normalize_seoul_event(item)
        if cand is None:
            return None
        desc = _strip_html(item.get("PROGRAM") or item.get("ETC_DESC"))
        return SourceRecord(
            candidate=cand,
            source="seoul",
            judge_intro=seoul_event_intro(item),
            classify_text=f"{cand.title}. {desc}"[:400],
            check_event_period=True,  # 행사기간 종료/미개막 Hard 판정
        )

    cid = str(item.get("contentid"))
    ctype = str(item.get("contenttypeid"))
    # 공식 상세(정본)·반복정보(detailInfo2)·Places businessStatus(폐업 음성 신호)를 병렬 조회.
    # detailInfo2 는 detailIntro2 가 놓치는 입장료·운영시간을 공식 데이터로 보강한다(§6.2 준수).
    # Places 는 보조·graceful — 실패해도 추천을 막지 않는다(§4.2·§6.7).
    intro, common, info, place = await asyncio.gather(
        tourapi.detail_intro(cid, ctype),
        tourapi.detail_common(cid),
        tourapi.detail_info(cid, ctype),
        gplaces.find_place(
            item.get("title") or "",
            float(item.get("mapy") or 0) or 0.0,
            float(item.get("mapx") or 0) or 0.0,
        ),
        return_exceptions=True,
    )
    intro = intro if isinstance(intro, dict) else {}
    common = common if isinstance(common, dict) else {}
    info = info if isinstance(info, list) else []
    place = place if isinstance(place, dict) else None

    # detailInfo2 로 빈 요금·운영시간 보강(공식 데이터만, 있을 때만).
    intro = enrich_intro(intro, info)

    cand = normalize_candidate(item, intro, common)
    if cand is None:
        return None

    return SourceRecord(
        candidate=cand,
        source="tour",
        judge_intro=intro,
        # 개방형 배제 의미분류용 텍스트(이름 + 공식 overview). 사실 생성 아님 — 공식 텍스트만.
        classify_text=f"{cand.title}. {_strip_html(common.get('overview'))}"[:400],
        place=place,
        check_event_period=(ctype == "85"),  # 날짜형만 종료/미개막 판정
        check_presence=True,  # Places 폐업 신호 교차확인
        allow_llm_hours=True,  # 운영시간 자유텍스트 LLM 재추출 허용
    )


async def _judge_record(
    rec: SourceRecord, ctx: RequestContext, cond: ParsedConditions, trace: Trace
) -> tuple[Candidate | None, TimingVerdict, BudgetVerdict, str]:
    """[check 가용성] SourceRecord → 운영/휴무/기간/폐업/예산 판정 → 3상태. Hard 는 (None,...).

    판정은 전부 결정론 코드(공식 데이터만). 성공 시 candidate.status/flags 를 세팅해 반환한다.
    """
    cand = rec.candidate

    # [judge-event] 날짜형(축제·공연·행사) 종료/미개막 → Hard 제외(끝난 콘텐츠 금지).
    if rec.check_event_period:
        period = judge_event_period(rec.judge_intro, ctx.start_at.date())
        if period in (EventPeriod.ENDED, EventPeriod.UPCOMING):
            trace.step(
                "event_excluded",
                title=cand.title,
                period=period.value,
                src=rec.source,
            )
            return None, TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN, ""

    # [judge-0] 폐업/임시휴업(Places 음성 신호·좌표 교차확인) → Hard 제외.
    if rec.check_presence:
        presence = judge_presence(rec.place, cand.lat, cand.lng)
        if presence is not PresenceVerdict.OPERATIONAL:
            trace.step("presence_excluded", title=cand.title, status=presence.value)
            return None, TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN, ""

    # [judge] 운영시간·휴무·행사기간 + 예산 → 3상태. Hard 충돌은 제외.
    timing, reason = judge_timing(rec.judge_intro, ctx.start_at, ctx.end_at)
    # regex가 '텍스트는 있으나 파싱 애매'로 UNCERTAIN → LLM 파서로 추출 재시도(OPEN 승격만).
    if rec.allow_llm_hours and should_retry_hours_with_llm(timing, reason):
        extracted = await parse_hours(
            operating_hours_text(rec.judge_intro), ctx.start_at
        )
        if extracted is not None:
            v, _r = judge_extracted_hours(extracted, ctx.start_at, ctx.end_at)
            if v is TimingVerdict.OPEN:
                trace.step("hours_llm", title=cand.title, from_=reason, to="open")
                timing = v
    budget = judge_budget(cand, cond)
    status, flags = resolve_status(cand, timing, budget, cond)
    if status is None:
        return None, timing, budget, ""  # Hard 제외
    cand.status = status
    cand.flags = flags
    return cand, timing, budget, rec.classify_text


async def _enrich(
    item: dict, ctx: RequestContext, cond: ParsedConditions, trace: Trace
) -> tuple[Candidate | None, TimingVerdict, BudgetVerdict, str]:
    """상세 조회→정규화→판정(운영/휴무/예산/폐업). Hard 충돌은 (None,...)로 제외.
    4번째 값은 개방형 배제 의미분류용 텍스트. search(_fetch_and_normalize)+check(_judge_record)
    두 단계로 분해돼 있으며(§6.2), 이 함수는 기존 파이프라인용으로 둘을 합성한다(동작 불변)."""
    rec = await _fetch_and_normalize(item)
    if rec is None:
        return None, TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN, ""
    return await _judge_record(rec, ctx, cond, trace)


EnrichResult = tuple[Candidate | None, TimingVerdict, BudgetVerdict, str]


def _pool_item_key(it: dict) -> str:
    """풀 아이템의 안정 키(반경 확대 시 이미 판정한 것 재판정 방지). 소스별."""
    if it.get("_src") == "seoul":
        return f"seoul:{it.get('_lat')},{it.get('_lng')}:{it.get('TITLE', '')}"
    return f"tour:{it.get('contentid')}"


def _etype_of(it: dict) -> Any:
    """풀 아이템 유형(fetch 단계 _etype, 없으면 contenttypeid 유추). 선호 랭킹용."""
    return it.get("_etype") or type_from_contenttype(it.get("contenttypeid"))


def _pool_dist(it: dict) -> float:
    """풀 아이템 거리(m). 없으면 큰 값(뒤로)."""
    try:
        return float(it.get("dist") or 1e12)
    except (TypeError, ValueError):
        return 1e12


async def _rerank_and_judge(
    pool: list[dict],
    ctx: RequestContext,
    cond: ParsedConditions,
    trace: Trace,
    enrich_pool: int,
) -> tuple[list[EnrichResult], int, set[str]]:
    """[select+judge] 풀을 (관심사 enum→의미유사도→실내외→거리)로 재정렬 후 상위 K 판정.

    P2 의미 재정렬(selection 전)을 단일 지점으로 모은 헬퍼 — A·B·반경 ladder 가 공용한다.
    반환: (유효 판정결과, Hard 제외 수, 판정에 소비한 아이템 키 집합). 사실·가용성은 _enrich 소유.
    """
    if not pool:
        return [], 0, set()
    intent = build_intent_text(cond, ctx.note)
    sims = await semantic_similarities(
        [pool_item_text(it) for it in pool], intent, trace
    )
    if cond.interests or cond.avoid_interests or cond.indoor_outdoor or intent:
        order = sorted(
            range(len(pool)),
            key=lambda i: (
                type_preference_rank(_etype_of(pool[i]), cond),
                -sims[i],
                io_rank(_etype_of(pool[i]), cond),
                _pool_dist(pool[i]),
            ),
        )
        pool = [pool[i] for i in order]
    batch = pool[:enrich_pool]
    seen = {_pool_item_key(it) for it in batch}
    results = await asyncio.gather(*(_enrich(it, ctx, cond, trace) for it in batch))
    hard = sum(1 for r in results if r[0] is None)
    judged = [r for r in results if r[0] is not None]
    return judged, hard, seen


async def collect_judged(
    lat: float,
    lng: float,
    ctx: RequestContext,
    cond: ParsedConditions,
    trace: Trace,
    *,
    first_pool: list[dict],
    enrich_pool: int,
    min_viable: int = _MIN_VIABLE,
) -> tuple[list[EnrichResult], int, int]:
    """[P1 적응형 반경] 1단계 풀로 판정 → 유효가 min_viable 미만이면 반경 ladder 로 확대 재조회.

    first_pool 은 호출부가 반경 1단계로 이미 조회해 넘긴 풀(parse_note/env 와 병렬 유지용).
    확장은 '선택지 부족'일 때만 — 밀집 지역은 트리거되지 않아 지연 불변. 이미 판정한 아이템은
    키로 걸러 재판정하지 않는다(사실·가용성은 _enrich 소유, 여기선 '얼마나 넓힐지'만 결정).
    반환: (유효 판정결과, Hard 제외 수, 최종 사용 반경).
    """
    judged, hard, seen = await _rerank_and_judge(
        first_pool, ctx, cond, trace, enrich_pool
    )
    used_radius = _RADIUS_LADDER[0]
    for radius in _RADIUS_LADDER[1:]:
        if len(judged) >= min_viable:
            break
        pool = await _fetch_pool(lat, lng, trace, ctx.start_at.date(), radius)
        pool = [it for it in pool if _pool_item_key(it) not in seen]
        j2, h2, seen2 = await _rerank_and_judge(pool, ctx, cond, trace, enrich_pool)
        judged += j2
        hard += h2
        seen |= seen2
        used_radius = radius
        trace.step(
            "radius_expand", radius=radius, viable=len(judged), hard_excluded=hard
        )
    return judged, hard, used_radius


def movement_from_leg(leg: dict | None) -> MovementInfo:
    """Tmap 구간 결과 → MovementInfo. None(실패/좌표없음) → Route unavailable(직선 위조 금지).

    도보시간은 예상값(estimate)이지 실제 ETA 보장이 아니다(PRD §6.2). _attach_movement·
    walk_route tool 공용 빌더(단일 지점)."""
    if leg is None:
        return MovementInfo(
            display="Route unavailable", provenance=Provenance.UNCONFIRMED
        )
    wm = leg["walk_minutes"]
    return MovementInfo(
        walk_minutes=wm,
        distance_m=leg["distance_m"],
        display=f"≈{wm} min walk",
        provenance=Provenance.ESTIMATE,
        path=leg["path"] or None,
    )


async def _attach_movement(cand: Candidate, olat: float, olng: float) -> None:
    """후보에 도보 이동정보(Tmap) 부착. 실패/좌표없음 → Route unavailable(직선 위조 금지)."""
    leg = None
    if cand.lat is not None and cand.lng is not None:
        leg = await tmap.pedestrian_route(olat, olng, cand.lat, cand.lng)
    cand.movement = movement_from_leg(leg)


async def recommend_a(
    ctx: RequestContext,
    trace: Trace,
    saved_interests: list[InterestCode] | None = None,
    prefer_shorter_walks: bool | None = None,
) -> RecommendData:
    lat, lng = resolve_start_coords(ctx.start_location)

    # [structure] 좌표 해석 + note 자연어 구조화(LLM)를 조회와 병렬로.
    # 확인 시트에서 교정한 조건이 오면 재파싱하지 않고 그대로 사용(사용자 교정 우선).
    if ctx.conditions is not None:
        cond = ctx.conditions
        pool, env = await asyncio.gather(
            _fetch_pool(lat, lng, trace, ctx.start_at.date()),
            get_environment(lat, lng, trace),
        )
    else:
        cond, pool, env = await asyncio.gather(
            parse_note(ctx.note),
            _fetch_pool(lat, lng, trace, ctx.start_at.date()),
            get_environment(lat, lng, trace),
        )
    # 저장 선호를 Request 우선으로 병합(note 침묵 시에만 관심사 Soft 채움, FR-L5).
    # 걷기 선호는 수치 변환 없이 trace 로만 기록(FR-L4, 순위 반영은 Soft 랭킹 B안).
    filled_from_saved = not cond.interests and bool(saved_interests)
    cond = merge_saved_interests(cond, saved_interests)
    trace.step(
        "structure",
        start=ctx.start_location.label,
        coords=f"{lat:.4f},{lng:.4f}",
        available_minutes=ctx.available_minutes,
        interests=[i.value for i in cond.interests],
        interests_from_saved=filled_from_saved,
        indoor_outdoor=cond.indoor_outdoor,
        prefer_shorter_walks=prefer_shorter_walks,
        free_only=cond.free_only,
        budget_krw=cond.budget_krw,
    )

    # [select+judge] 의미 관련도 우선 선발(P2) + 적응형 반경(P1): 1단계 풀을 (관심사 enum →
    # 의미 유사도 → 실내외 → 거리)로 재정렬해 상위 K 를 판정하고, 유효가 부족하면 반경을 넓혀
    # 재조회한다(강제 채움 아님 — 선택지가 2개도 안 될 때만 확대). 사실·가용성은 _enrich 소유.
    judged, excluded_hard, used_radius = await collect_judged(
        lat, lng, ctx, cond, trace, first_pool=pool, enrich_pool=_ENRICH_POOL
    )
    valid = list(judged)
    radius_notices = (
        [_RADIUS_EXPANDED_NOTICE] if used_radius > _RADIUS_LADDER[0] else []
    )

    # [filter-places] 명시 장소 제외(B4, 결정론 title 매칭) — 사용자가 이름 댄 장소 hard 제거.
    place_ids = match_excluded_places(
        [(c.id, c.title) for (c, _, _, _) in valid], cond.exclude_places
    )
    if place_ids:
        valid = [v for v in valid if v[0].id not in place_ids]
        trace.step("exclude_places", places=cond.exclude_places, removed=len(place_ids))

    # [classify] per-candidate LLM 판정(§6.4) — 실내/외(유형추측 대체) + 개방형 정성선호 적합도.
    #   한 콜. 사실 생성 아님(공식 텍스트 분류). 실내외 Hard/Soft + 정성 Soft 순위에 쓴다.
    io_verdicts: dict[str, str] = {}
    vibe_ranks: dict[str, int] = {}
    io_notices: list[str] = []
    if (cond.indoor_outdoor or cond.open_preferences) and valid:
        verdicts = await classify_places(
            [(c.id, txt) for (c, _, _, txt) in valid],
            trace,
            cond.open_preferences,
        )
        io_verdicts = {cid: v.setting for cid, v in verdicts.items()}
        vibe_ranks = {cid: (0 if v.fits_vibe else 1) for cid, v in verdicts.items()}
        # "실내만/실외만"(strict, §6.7) → 반대로 '확신 분류'된 후보만 Hard 제외.
        #   unknown·동일은 유지(확신 없을 때 유효 후보 제거 금지 — A1식 보수).
        if cond.indoor_outdoor and cond.indoor_outdoor_strict:
            opposite = "outdoor" if cond.indoor_outdoor == "indoor" else "indoor"
            before = len(valid)
            valid = [v for v in valid if io_verdicts.get(v[0].id) != opposite]
            removed = before - len(valid)
            if removed:
                trace.step(
                    "io_strict_exclude", pref=cond.indoor_outdoor, removed=removed
                )
                io_notices.append(
                    f"Showing {cond.indoor_outdoor} options only — some "
                    f"{opposite} results were set aside."
                )

    # [filter] 개방형 명시 배제(옵션3): LLM은 매칭만 판단, 선별·0건-세이프는 코드(domain).
    #   - 사실 생성 없음(이미 판정된 fact 후보 위에서 '고르기'만). graceful=빈 집합.
    exclude_ids: set[str] = set()
    if cond.exclude_concepts and valid:
        exclude_ids = await classify_excluded(
            [(c.id, txt) for (c, _, _, txt) in valid], cond.exclude_concepts, trace
        )
    by_id = {c.id: (c, t, b) for (c, t, b, _) in valid}
    kept_ids, notices, applied = select_with_exclusion(
        [c.id for (c, _, _, _) in valid],
        exclude_ids,
        cond.exclude_concepts,
        _MAX_CANDIDATES,
    )
    if notices:  # 0건-세이프 발동 — trace 로 증빙
        trace.step("exclude_safe_fallback", concepts=cond.exclude_concepts)
    # 반경 확대·실내외 strict 안내를 함께 전달(투명 — 왜 이 결과인지 사용자에게 고지).
    notices = [*radius_notices, *io_notices, *notices]
    kept = [by_id[i] for i in kept_ids]
    candidates = [c for c, _, _ in kept]
    fits = sum(1 for c in candidates if c.status.value == "fits")
    alt = sum(1 for c in candidates if c.status.value == "alternative")
    trace.step(
        "judge",
        considered=len(judged) + excluded_hard,
        excluded_hard=excluded_hard,
        excluded_pref=len(applied),
        fits=fits,
        alternative=alt,
        check_needed=len(candidates) - fits - alt,
    )

    # [route] 후보별 도보 이동정보(Tmap) 병렬 부착
    await asyncio.gather(*(_attach_movement(c, lat, lng) for c in candidates))
    with_path = sum(1 for c in candidates if c.movement and c.movement.path)
    trace.step("route", with_path=with_path, total=len(candidates))

    # [explain] 확정 근거 기반 Reason 선택(0~2개). 최근접 1개만 M03.
    for i, (cand, timing, budget) in enumerate(kept):
        cand.reasons = select_reasons(
            cand, cond, timing, budget, is_nearest=(i == 0 and len(kept) > 1)
        )
    trace.step("explain", with_reasons=sum(1 for c in candidates if c.reasons))

    # [compose] 표시 순서: 등급(fits→alternative→check_needed) 우선, 같은 등급 안에서
    # 관심사 선호↑·비선호↓(Soft, 제외 아님), 그다음 거리순. candidates 는 이미 거리순 →
    # display_sort_key 로 '안정 정렬'하면 같은 키 안에서 거리순이 유지된다(domain/ranking).
    candidates.sort(
        key=lambda c: display_sort_key(
            c, cond, adverse=env.adverse, io_verdicts=io_verdicts, vibe_ranks=vibe_ranks
        )
    )
    trace.step(
        "compose", kept=len(candidates), order=[c.status.value for c in candidates]
    )
    origin = StartLocation(label=ctx.start_location.label, lat=lat, lng=lng)
    return RecommendData(
        candidates=candidates,
        origin=origin,
        conditions=cond,
        notices=notices,
        environment=env,
    )
