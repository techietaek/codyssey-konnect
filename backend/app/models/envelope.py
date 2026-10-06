"""공통 응답 봉투(Envelope).

모든 API 응답은 이 봉투로 감싼다. 정상 결과는 ok=True + data,
시스템 예외(FR-C7)는 ok=False + error. trace_id 로 다단계 동작 추적(NFR-08).
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorInfo(BaseModel):
    code: str
    message: str  # 사용자-facing(영어 우선). 내부 용어 노출 금지.


class Envelope(BaseModel, Generic[T]):
    ok: bool
    trace_id: str
    data: T | None = None
    error: ErrorInfo | None = None

    @classmethod
    def success(cls, data: T, trace_id: str) -> Envelope[T]:
        return cls(ok=True, trace_id=trace_id, data=data)

    @classmethod
    def failure(cls, code: str, message: str, trace_id: str) -> Envelope[T]:
        return cls(
            ok=False, trace_id=trace_id, error=ErrorInfo(code=code, message=message)
        )
