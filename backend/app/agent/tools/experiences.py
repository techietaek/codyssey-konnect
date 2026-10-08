"""경험 조회·가용성 판정 tool (rollout 2a, 설계 §6.3).

agentic 루프가 조합할 **코드 소유 사실 tool** 2종을 얇게 노출한다. 기존 orchestrator 의
멀티소스 fetch·정규화·결정론 판정을 재사용(정본 유지) — 여기선 '도구 경계'만 만든다.

신뢰 경계(§6.4):
- `search_experiences` = 가용성 **판정 전**의 사실 후보(멀티소스 정규화). 요청(ctx)·선호 무관.
- `check_availability` = 운영/휴무/기간/폐업/예산 판정 → fits/check/Hard제외. **가용성=코드.**
- LLM 선별(classify/finalize)은 4단계 — 여기엔 없다. 두 tool 모두 graceful·trace.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

from app.agent.context import RequestContext
from app.agent.orchestrator import (
    _ENRICH_POOL,
    SourceRecord,
    _fetch_and_normalize,
    _fetch_pool,
    _judge_record,
)
from app.core.trace import Trace
from app.domain.budget import BudgetVerdict
from app.domain.timing import TimingVerdict
from app.models.recommend import Candidate, ParsedConditions


@dataclass
class CheckedCandidate:
    """가용성 판정을 통과한 후보 + 판정 결과(하위 선별·Reason·루트가 소비)."""

    candidate: Candidate  # status/flags 가 세팅된 상태
    timing: TimingVerdict
    budget: BudgetVerdict
    classify_text: str  # 개방형 배제 의미분류용(공식 텍스트)


async def search_experiences(
    lat: float,
    lng: float,
    on_date: date,
    trace: Trace,
    limit: int = _ENRICH_POOL,
) -> list[SourceRecord]:
    """[사실] 좌표·방문일 기준 멀티소스 조회 → 공통 Candidate 정규화(판정 전).

    반경·거리필터·병합·dedup 은 `_fetch_pool`(§6.2), 상세·정규화는 `_fetch_and_normalize`.
    선호·시간 판정은 하지 않는다 — 가용성은 check_availability 가 소유. 거리순 상위 limit 만.
    """
    pool = await _fetch_pool(lat, lng, trace, on_date)
    records = await asyncio.gather(*(_fetch_and_normalize(it) for it in pool[:limit]))
    found = [r for r in records if r is not None]
    trace.step(
        "tool.search_experiences",
        pool=len(pool),
        normalized=len(found),
        sources=sorted({r.source for r in found}),
    )
    return found


async def check_availability(
    records: list[SourceRecord],
    ctx: RequestContext,
    cond: ParsedConditions,
    trace: Trace,
) -> list[CheckedCandidate]:
    """[가용성] 레코드별 운영/휴무/기간/폐업/예산 판정 → fits/check. Hard 충돌은 제외.

    결정론 코드만(공식 데이터). LLM 선별 입력에는 **이 통과분만** 들어간다(§6.4).
    """
    results = await asyncio.gather(
        *(_judge_record(rec, ctx, cond, trace) for rec in records)
    )
    checked = [
        CheckedCandidate(candidate=c, timing=t, budget=b, classify_text=txt)
        for (c, t, b, txt) in results
        if c is not None
    ]
    hard_excluded = len(records) - len(checked)
    fits = sum(1 for c in checked if c.candidate.status.value == "fits")
    trace.step(
        "tool.check_availability",
        considered=len(records),
        available=len(checked),
        hard_excluded=hard_excluded,
        fits=fits,
    )
    return checked
