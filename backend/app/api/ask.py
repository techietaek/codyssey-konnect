"""RAG Q&A 라우터 (FAQ·여행정보·콘텐츠) — PRD §6.5·FR-C8.

검색 근거 범위 안에서만 답변하고, 근거가 없으면 생성하지 않고 refuse 한다.
얇게 유지 — 검색·판정·답변은 rag/ 가 담당. 추후 Agent 의 `rag_search` tool 로 재사용.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.trace import Trace
from app.models.envelope import Envelope
from app.models.rag import AskRequest, RagAnswer
from app.rag.retrieve import answer_question

router = APIRouter(prefix="/api", tags=["rag"])


@router.post("/ask", response_model=Envelope[RagAnswer])
async def ask(req: AskRequest) -> Envelope[RagAnswer]:
    trace = Trace()
    data = await answer_question(req.question, trace)
    return Envelope.success(data=data, trace_id=trace.trace_id)
