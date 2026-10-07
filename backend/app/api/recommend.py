"""즉시 추천(A) 라우터.

A2: 입력 검증 → 구조화 → 공식 API(TourAPI) 조회 → 정규화 후보 반환.
판정(3상태·시간충돌)은 A3, Reason·지도는 A4·A5에서 더한다.
라우터는 얇게 유지 — 파이프라인은 agent/orchestrator, 조회는 sources/, 판정은 domain/.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.agent.context import RequestContext
from app.agent.note_parser import parse_note
from app.agent.orchestrator import recommend_a
from app.core.auth import AuthUser, get_optional_user
from app.core.trace import Trace
from app.db.preferences import get_preferences
from app.domain.input_validation import validate_available_time
from app.models.envelope import Envelope
from app.models.recommend import (
    InterestCode,
    ParsedConditions,
    ParseRequest,
    RecommendData,
    RecommendRequest,
)

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/parse", response_model=Envelope[ParsedConditions])
async def parse(req: ParseRequest) -> Envelope[ParsedConditions]:
    """확인 시트용 — note 를 '이해한 조건'으로 구조화(추천 조회 없음, 경량).

    사용자가 확인/수정한 뒤 /recommend 에 conditions 로 돌려보낸다.
    """
    trace = Trace()
    cond = await parse_note(req.note)
    return Envelope.success(data=cond, trace_id=trace.trace_id)


@router.post("/recommend", response_model=Envelope[RecommendData])
async def recommend(
    req: RecommendRequest,
    user: Annotated[AuthUser | None, Depends(get_optional_user)] = None,
) -> Envelope[RecommendData]:
    trace = Trace()
    # [auth] 선택적 신원(익명/정식). 비로그인도 허용(FR-L1 첫 추천). 영속은 L1c.
    trace.step(
        "auth",
        user=user.id if user else None,
        anonymous=bool(user and user.is_anonymous),
    )

    # [validate] 추천 전 입력 경계 검증 (FR-A2·A3). 위반 시 ValidationFailure →
    # main.py 핸들러가 422 Envelope(ok=False)로 변환. 시스템 예외·0건과 구분.
    validate_available_time(req.start_at, req.end_at)

    # [structure] 검증 통과 입력을 Request Context로 구조화. note 원문은 보존.
    ctx = RequestContext(
        start_location=req.start_location,
        start_at=req.start_at,
        end_at=req.end_at,
        note=req.note,
        conditions=req.conditions,
    )

    # [preference] 로그인 사용자면 저장 선호를 읽어 Soft 신호로 전달(Request 우선 병합은
    # 파이프라인에서). 비로그인/익명·미온보딩은 행이 없어 None → 영향 없음(FR-L5).
    saved_interests: list[InterestCode] | None = None
    prefer_shorter_walks: bool | None = None
    if user is not None:
        pref = await get_preferences(user.id)
        if pref:
            saved_interests = [InterestCode(i) for i in (pref.get("interests") or [])]
            prefer_shorter_walks = pref.get("prefer_shorter_walks")

    # [fetch → judge → route] 조회·정규화·판정·도보 이동. 시스템 예외
    # (ExternalSourceError)는 main.py 핸들러가 503으로 변환. 0건은 정상(빈 candidates).
    data = await recommend_a(ctx, trace, saved_interests, prefer_shorter_walks)
    return Envelope.success(data=data, trace_id=trace.trace_id)
