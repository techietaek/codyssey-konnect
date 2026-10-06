"""즉시 추천(A) 라우터.

A2: 입력 검증 → 구조화 → 공식 API(TourAPI) 조회 → 정규화 후보 반환.
판정(3상태·시간충돌)은 A3, Reason·지도는 A4·A5에서 더한다.
라우터는 얇게 유지 — 파이프라인은 agent/orchestrator, 조회는 sources/, 판정은 domain/.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.context import RequestContext
from app.agent.orchestrator import recommend_a
from app.core.trace import Trace
from app.domain.input_validation import validate_available_time
from app.models.envelope import Envelope
from app.models.recommend import RecommendData, RecommendRequest

router = APIRouter(prefix="/api", tags=["recommend"])


@router.post("/recommend", response_model=Envelope[RecommendData])
async def recommend(req: RecommendRequest) -> Envelope[RecommendData]:
    trace = Trace()

    # [validate] 추천 전 입력 경계 검증 (FR-A2·A3). 위반 시 ValidationFailure →
    # main.py 핸들러가 422 Envelope(ok=False)로 변환. 시스템 예외·0건과 구분.
    validate_available_time(req.start_at, req.end_at)

    # [structure] 검증 통과 입력을 Request Context로 구조화. note 원문은 보존.
    ctx = RequestContext(
        start_location=req.start_location,
        start_at=req.start_at,
        end_at=req.end_at,
        note=req.note,
    )

    # [fetch → compose] 공식 API 조회·정규화. 시스템 예외(ExternalSourceError)는
    # main.py 핸들러가 503으로 변환. 0건은 정상 결과(빈 candidates)로 내려보낸다.
    candidates = await recommend_a(ctx, trace)
    data = RecommendData(candidates=candidates)
    return Envelope.success(data=data, trace_id=trace.trace_id)
