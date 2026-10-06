"""즉시 추천(A) 라우터 — Phase 0 스텁.

계약(RecommendRequest/RecommendData)만 고정하는 단계다.
하드코딩 후보 1개를 반환하되 '신뢰 불변식을 지키는 형태'로 만든다:
- 가격 미확인을 free 로 매핑하지 않고 PriceStatus.UNKNOWN + 미확인 flag 로 표현.
- 모든 사실값에 provenance 표기.
실제 조회/판정/LLM 설명은 Phase 1(A2~A5)에서 이 자리를 대체한다.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.trace import Trace
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
    trace.step(
        "structure",
        start_location=req.start_location,
        start_time=req.start_time,
        end_time=req.end_time,
    )
    trace.step("compose", note="phase0 stub — single hardcoded candidate")
    data = RecommendData(candidates=[_stub_candidate()])
    return Envelope.success(data=data, trace_id=trace.trace_id)
