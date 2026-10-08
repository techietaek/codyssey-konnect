"""classify_places(실내/외 LLM 분류) + io_rank_with_verdict(순위) 테스트 (rollout 4).

LLM 은 RunnableLambda 로 모킹(결정론). 검증: 분류 매핑·graceful·verdict 우선 순위·
unknown 중립·verdict 없을 때 유형 fallback.
"""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableLambda

from app.agent import classify as cl
from app.agent.classify import PlaceClassification, _PlaceIO, classify_places
from app.core.trace import Trace
from app.domain.ranking import io_rank_with_verdict
from app.models.recommend import (
    Candidate,
    ExperienceType,
    ParsedConditions,
    ResultStatus,
)


class _FakeLLM:
    def __init__(self, result, boom=False):
        self.result = result
        self.boom = boom

    def with_structured_output(self, model):
        def _run(_inp):
            if self.boom:
                raise RuntimeError("llm down")
            return self.result

        return RunnableLambda(_run)


def _patch(monkeypatch, result=None, boom=False):
    monkeypatch.setattr(cl, "ChatOpenAI", lambda **kw: _FakeLLM(result, boom))


def test_classify_maps_verdicts(monkeypatch):
    result = PlaceClassification(
        places=[
            _PlaceIO(id="a", setting="indoor"),
            _PlaceIO(id="b", setting="outdoor"),
            _PlaceIO(id="c", setting="unknown"),
            _PlaceIO(id="x", setting="indoor"),  # valid_ids 밖 → 버려짐
        ]
    )
    _patch(monkeypatch, result)
    out = asyncio.run(
        classify_places([("a", "museum"), ("b", "park"), ("c", "??")], Trace())
    )
    assert out == {"a": "indoor", "b": "outdoor", "c": "unknown"}


def test_classify_empty_items_no_call():
    assert asyncio.run(classify_places([], Trace())) == {}


def test_classify_graceful_on_failure(monkeypatch):
    _patch(monkeypatch, boom=True)
    assert asyncio.run(classify_places([("a", "x")], Trace())) == {}


# ── io_rank_with_verdict (verdict 우선, 유형 fallback) ──
def _cand(etype):
    return Candidate(id="z", title="t", type=etype, status=ResultStatus.CHECK_NEEDED)


def test_verdict_overrides_type():
    cond = ParsedConditions(indoor_outdoor="indoor")
    # 유형상 outdoor(역사방문)지만 verdict=indoor → 일치(0)
    assert (
        io_rank_with_verdict(_cand(ExperienceType.HISTORIC_VISIT), cond, "indoor") == 0
    )
    # verdict=outdoor → 불일치(2)
    assert io_rank_with_verdict(_cand(ExperienceType.EXHIBITION), cond, "outdoor") == 2


def test_unknown_verdict_is_neutral():
    cond = ParsedConditions(indoor_outdoor="indoor")
    assert (
        io_rank_with_verdict(_cand(ExperienceType.HISTORIC_VISIT), cond, "unknown") == 1
    )


def test_no_verdict_falls_back_to_type():
    cond = ParsedConditions(indoor_outdoor="indoor")
    # verdict 없음 → 유형 휴리스틱: EXHIBITION=실내=일치(0)
    assert io_rank_with_verdict(_cand(ExperienceType.EXHIBITION), cond, None) == 0
    # HISTORIC_VISIT=야외=불일치(2)
    assert io_rank_with_verdict(_cand(ExperienceType.HISTORIC_VISIT), cond, None) == 2


def test_no_preference_is_neutral():
    cond = ParsedConditions()  # indoor_outdoor None
    assert io_rank_with_verdict(_cand(ExperienceType.EXHIBITION), cond, "outdoor") == 1
