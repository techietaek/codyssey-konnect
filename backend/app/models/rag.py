"""RAG(FAQ·여행정보·콘텐츠 Q&A) 계약 (PRD §6.5·FR-C8).

신뢰 불변식(CLAUDE §4.5·§6):
- 답변은 검색된 근거 범위 안에서만. 근거 없으면 생성하지 않고 `grounded=False`로 refuse.
- 사실(가격·운영시간·예약)은 RAG가 아니라 공식 API 정본 — RAG는 참고지식 한정.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KbChunk(BaseModel):
    """지식베이스 청크(적재·검색 단위)."""

    id: str  # f"{doc_id}#{idx}"
    text: str
    doc_id: str
    doc_title: str
    section: str


class RagCitation(BaseModel):
    """답변 근거 출처(검색된 청크) — '무엇을 근거로 답했는지' 투명 공개."""

    source: str  # 예: "Money and language basics · Tipping"
    snippet: str


class RagAnswer(BaseModel):
    answer: str
    grounded: bool  # 검색 근거가 있었는지(없으면 생성 안 함)
    citations: list[RagCitation] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str
