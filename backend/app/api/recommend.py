"""즉시 추천(A) 라우터 — Phase 0 스텁.

계약(RecommendRequest/RecommendData)만 고정하는 단계다.
하드코딩 후보 1개를 반환하되 '신뢰 불변식을 지키는 형태'로 만든다:
- 가격 미확인을 free 로 매핑하지 않고 PriceStatus.UNKNOWN + 미확인 flag 로 표현.
- 모든 사실값에 provenance 표기.
실제 조회/판정/LLM 설명은 Phase 1(A2~A5)에서 이 자리를 대체한다.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.context import RequestContext
from app.core.trace import Trace
from app.domain.input_validation import validate_available_time
from app.models.envelope import Envelope
from app.models.recommend import (
    Candidate,
    ExperienceType,
    MovementInfo,
    OfficialLink,
    PriceInfo,
    PriceStatus,
    Provenance,
    Reason,
    RecommendData,
    RecommendRequest,
    ResultStatus,
    TimeInfo,
    UnconfirmedFlag,
)

router = APIRouter(prefix="/api", tags=["recommend"])


def _stub_candidate() -> Candidate:
    """Phase 0 데모용 고정 후보 1개 (불변식 준수 형태)."""
    return Candidate(
        id="stub-gyeongbokgung",
        title="Gyeongbokgung Palace",
        type=ExperienceType.HISTORIC_VISIT,
        status=ResultStatus.CHECK_NEEDED,
        reasons=[
            Reason(
                code="I02", text="Matches your interest in palaces and historic sites"
            ),
        ],
        time=TimeInfo(display="Open 09:00–18:00", provenance=Provenance.CONFIRMED),
        # 가격 미확인을 free 로 추정하지 않는다 → UNKNOWN + flag.
        price=PriceInfo(
            status=PriceStatus.UNKNOWN,
            display="Price needs checking",
            raw=None,
            provenance=Provenance.UNCONFIRMED,
        ),
        movement=MovementInfo(
            walk_minutes=12,
            distance_m=950,
            display="≈12 min walk",
            provenance=Provenance.ESTIMATE,
        ),
        flags=[UnconfirmedFlag(text="Price needs checking")],
        image_url=None,
        official_links=[
            OfficialLink(
                label="View official details",
                url="https://english.visitkorea.or.kr/",
            )
        ],
    )


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
    trace.step(
        "structure",
        start_location=ctx.start_location.label,
        available_minutes=ctx.available_minutes,
        has_note=bool(ctx.note),
    )

    # [compose] Phase 1 A1: 조회/판정 전이므로 스텁 후보 유지(계약 고정).
    # A2~A5에서 이 자리를 실제 조회·판정·설명으로 대체한다.
    trace.step("compose", note="A1 stub — single hardcoded candidate")
    data = RecommendData(candidates=[_stub_candidate()])
    return Envelope.success(data=data, trace_id=trace.trace_id)
