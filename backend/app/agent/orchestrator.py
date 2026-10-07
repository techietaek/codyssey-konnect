"""즉시 추천(A) 파이프라인.

structure(입력+note LLM 구조화) → fetch(공식 API) → judge(운영/휴무/예산) →
route(Tmap) → explain(Reason) → compose. 한 소스 실패가 전체 실패로 번지지 않게
부분 실패를 허용한다(CLAUDE §4.2). 판정·Reason은 코드로, LLM은 note 구조화만.
"""

from __future__ import annotations

import asyncio

from app.agent.context import RequestContext
from app.agent.exclude_classifier import classify_excluded
from app.agent.hours_parser import parse_hours
from app.agent.note_parser import parse_note
from app.core.exceptions import ExternalSourceError
from app.core.trace import Trace
from app.domain.budget import BudgetVerdict, judge_budget
from app.domain.curation import is_cultural_experience
from app.domain.exclusion import select_with_exclusion
from app.domain.locations import resolve_start_coords
from app.domain.normalize import (
    _strip_html,
    enrich_intro,
    normalize_candidate,
    type_from_contenttype,
)
from app.domain.operational import PresenceVerdict, judge_presence
from app.domain.preferences_merge import merge_saved_interests
from app.domain.ranking import display_sort_key, type_preference_rank
from app.domain.reasons import select_reasons
from app.domain.status import resolve_status
from app.domain.timing import (
    TimingVerdict,
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
from app.sources import gplaces, tmap, tourapi

# 문화경험 콘텐츠 타입(EngService2): 관광지·문화시설·축제/공연/행사.
# (식당·쇼핑·숙박 등은 제외 — PRD §6.4)
_CULTURAL_TYPES = (76, 78, 85)
_SEARCH_RADIUS_M = 1500
_MAX_CANDIDATES = 4
_ENRICH_POOL = 8  # 판정 후 Hard 제외분을 다음 후보로 대체하기 위한 보강 범위


async def _fetch_pool(lat: float, lng: float, trace: Trace) -> list[dict]:
    """문화 타입별 목록을 병렬 조회 → 병합·중복제거·거리순. 전부 실패 시 예외."""
    results = await asyncio.gather(
        *(
            tourapi.location_based_list(lat, lng, _SEARCH_RADIUS_M, t)
            for t in _CULTURAL_TYPES
        ),
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
                merged[cid] = it

    def _dist(it: dict) -> float:
        try:
            return float(it.get("dist") or 1e12)
        except ValueError:
            return 1e12

    pool = sorted(merged.values(), key=_dist)
    trace.step("fetch", pool=len(pool), sources_failed=failed)
    return pool


async def _enrich(
    item: dict, ctx: RequestContext, cond: ParsedConditions, trace: Trace
) -> tuple[Candidate | None, TimingVerdict, BudgetVerdict, str]:
    """상세 조회→정규화→판정(운영/휴무/예산/폐업). Hard 충돌은 (None,...)로 제외.
    4번째 값은 개방형 배제 의미분류용 텍스트(이름+공식 overview, 공식 데이터만)."""
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
        return None, TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN, ""

    # 개방형 배제 의미분류용 텍스트(이름 + 공식 overview). 사실 생성 아님 — 공식 텍스트만.
    classify_text = f"{cand.title}. {_strip_html(common.get('overview'))}"[:400]

    # [judge-0] 폐업/임시휴업(Places 음성 신호·좌표 교차확인) → Hard 제외.
    presence = judge_presence(place, cand.lat, cand.lng)
    if presence is not PresenceVerdict.OPERATIONAL:
        trace.step("presence_excluded", title=cand.title, status=presence.value)
        return None, TimingVerdict.UNCERTAIN, BudgetVerdict.UNKNOWN, ""

    # [judge] 운영시간·휴무·행사기간 + 예산 → 3상태. Hard 충돌은 제외.
    timing, reason = judge_timing(intro, ctx.start_at, ctx.end_at)
    # regex가 '텍스트는 있으나 파싱 애매'로 UNCERTAIN → LLM 파서로 추출 재시도(OPEN 승격만).
    if should_retry_hours_with_llm(timing, reason):
        extracted = await parse_hours(operating_hours_text(intro), ctx.start_at)
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
    return cand, timing, budget, classify_text


async def _attach_movement(cand: Candidate, olat: float, olng: float) -> None:
    """후보에 도보 이동정보(Tmap) 부착. 실패/좌표없음 → Route unavailable(직선 위조 금지)."""
    route = None
    if cand.lat is not None and cand.lng is not None:
        route = await tmap.pedestrian_route(olat, olng, cand.lat, cand.lng)
    if route is None:
        cand.movement = MovementInfo(
            display="Route unavailable", provenance=Provenance.UNCONFIRMED
        )
        return
    wm = route["walk_minutes"]
    cand.movement = MovementInfo(
        walk_minutes=wm,
        distance_m=route["distance_m"],
        display=f"≈{wm} min walk",
        provenance=Provenance.ESTIMATE,  # 예상값 — 실제 ETA 보장 아님
        path=route["path"] or None,
    )


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
        pool = await _fetch_pool(lat, lng, trace)
    else:
        cond, pool = await asyncio.gather(
            parse_note(ctx.note), _fetch_pool(lat, lng, trace)
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
        prefer_shorter_walks=prefer_shorter_walks,
        free_only=cond.free_only,
        budget_krw=cond.budget_krw,
    )

    # [select] 관심사 우선 선발(FR-B4 Soft B안): 조회 풀(반경 1500m 내, 거리순)을 관심사
    # 우선으로 '안정 정렬' → 관심사 맞는 후보가 조금 멀어도 판정·선발에 들어온다(거리는
    # 같은 관심사 안에서 보존). 관심사 미언급이면 모두 중립이라 거리순 그대로.
    if cond.interests or cond.avoid_interests:
        pool.sort(
            key=lambda it: type_preference_rank(
                type_from_contenttype(it.get("contenttypeid")), cond
            )
        )

    # 관심사 우선 순으로 넉넉히 보강·판정 후 '유효한' 소수만 유지(제외분을 다음 후보로
    # 대체. 부적합 후보로 숫자 채우는 것 아님 — 유효 후보 중 최대 4개).
    results = await asyncio.gather(
        *(_enrich(it, ctx, cond, trace) for it in pool[:_ENRICH_POOL])
    )
    excluded_hard = sum(1 for r in results if r[0] is None)
    valid = [(c, t, b, txt) for (c, t, b, txt) in results if c is not None]

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
    kept = [by_id[i] for i in kept_ids]
    candidates = [c for c, _, _ in kept]
    fits = sum(1 for c in candidates if c.status.value == "fits")
    alt = sum(1 for c in candidates if c.status.value == "alternative")
    trace.step(
        "judge",
        considered=len(results),
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
    candidates.sort(key=lambda c: display_sort_key(c, cond))
    trace.step(
        "compose", kept=len(candidates), order=[c.status.value for c in candidates]
    )
    origin = StartLocation(label=ctx.start_location.label, lat=lat, lng=lng)
    return RecommendData(
        candidates=candidates, origin=origin, conditions=cond, notices=notices
    )
