"""공통 예외 (FR-C7).

시스템 예외(데이터·AI·네트워크 오류 → 재시도·안내 대상)와
정상 Product 결과(0건 등 — 예외 아님)를 명확히 구분한다.
0건·추가 확인 필요는 예외가 아니라 정상 응답으로 표현한다.
"""

from __future__ import annotations


class KonnectError(Exception):
    """KONNECT 공통 예외 베이스."""

    code: str = "internal_error"
    http_status: int = 500
    user_message: str = "Something went wrong. Please try again."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.user_message)


class SystemError(KonnectError):
    """시스템 예외 — 데이터/AI/네트워크 오류. 전 구간 공통 처리(재시도·안내)."""

    code = "system_error"
    http_status = 503
    user_message = "A system error occurred. Please try again in a moment."


class ExternalSourceError(SystemError):
    """외부 API(공식 데이터·지도 등) 호출 실패."""

    code = "external_source_error"
    user_message = "Could not reach an external service. Please try again."


class ValidationFailure(KonnectError):
    """입력 검증 실패(추천 전 입력 오류·제한, FR-A3). 시스템 예외 아님."""

    code = "validation_error"
    http_status = 422
    user_message = "Please check your input and try again."
