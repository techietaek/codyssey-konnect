"""search_experiences / check_availability tool 경계 테스트 (rollout 2a).

외부 I/O 는 monkeypatch 로 가짜 소스·판정 입력을 주입하고, 두 tool 이 '사실 조회'와
'가용성 판정'을 올바르게 분리·수행하는지 본다(가용성=코드, Hard 제외 반영).
tool 은 import 시점에 헬퍼를 바인딩하므로 experiences 모듈 네임스페이스를 패치한다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.agent import orchestrator as orch
from app.agent.context import RequestContext
from app.agent.tools import experiences as exp
from app.core.trace import Trace
from app.domain.budget import BudgetVerdict
from app.domain.timing import TimingVerdict
from app.models.recommend import (
    Candidate,
    ParsedConditions,
    PriceInfo,
    PriceStatus,
    Provenance,
    ResultStatus,
    StartLocation,
)


def _ctx():
    return RequestContext(
        start_location=StartLocation(label="x", lat=37.57, lng=126.98),
        start_at=datetime(2026, 10, 8, 13, 0),
        end_at=datetime(2026, 10, 8, 18, 0),
    )


def _cand(cid: str) -> Candidate:
    return Candidate(
        id=cid,
        title=f"Place {cid}",
        status=ResultStatus.CHECK_NEEDED,
        price=PriceInfo(
            status=PriceStatus.FREE,
            display="Free",
            raw="free",
            provenance=Provenance.CONFIRMED,
        ),
        lat=37.57,
        lng=126.98,
    )


def _rec(cid: str) -> orch.SourceRecord:
    return orch.SourceRecord(
        candidate=_cand(cid),
        source="tour",
        judge_intro={},
        classify_text=f"Place {cid}",
    )


def test_search_normalizes_pool_and_skips_none(monkeypatch):
    pool = [{"_src": "tour", "id": "a"}, {"_src": "tour", "id": "b"}, {"_src": "x"}]

    async def fake_pool(lat, lng, trace, on_date):
        return pool

    async def fake_norm(item):
        return None if item.get("_src") == "x" else _rec(item["id"])

    monkeypatch.setattr(exp, "_fetch_pool", fake_pool)
    monkeypatch.setattr(exp, "_fetch_and_normalize", fake_norm)

    out = asyncio.run(
        exp.search_experiences(37.57, 126.98, _ctx().start_at.date(), Trace())
    )
    assert [r.candidate.id for r in out] == ["a", "b"]  # None drop


def test_search_respects_limit(monkeypatch):
    pool = [{"_src": "tour", "id": str(i)} for i in range(20)]

    async def fake_pool(lat, lng, trace, on_date):
        return pool

    async def fake_norm(item):
        return _rec(item["id"])

    monkeypatch.setattr(exp, "_fetch_pool", fake_pool)
    monkeypatch.setattr(exp, "_fetch_and_normalize", fake_norm)

    out = asyncio.run(
        exp.search_experiences(37.57, 126.98, _ctx().start_at.date(), Trace(), limit=5)
    )
    assert len(out) == 5


def test_check_filters_hard_excluded(monkeypatch):
    async def fake_judge(rec, ctx, cond, trace):
        if rec.candidate.id == "bad":
            return None, TimingVerdict.CLOSED, BudgetVerdict.UNKNOWN, ""
        rec.candidate.status = ResultStatus.FITS
        return rec.candidate, TimingVerdict.OPEN, BudgetVerdict.OK, rec.classify_text

    monkeypatch.setattr(exp, "_judge_record", fake_judge)

    recs = [_rec("good"), _rec("bad")]
    out = asyncio.run(check_availability_run(recs))
    assert [c.candidate.id for c in out] == ["good"]  # Hard 제외분 빠짐
    assert out[0].candidate.status is ResultStatus.FITS
    assert out[0].timing is TimingVerdict.OPEN


def check_availability_run(recs):
    return exp.check_availability(recs, _ctx(), ParsedConditions(), Trace())
