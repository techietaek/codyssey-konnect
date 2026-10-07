"""Supabase 세션 JWT 검증 (Phase 2 L1a).

프론트가 Supabase Auth(Google·Anonymous)로 받은 세션 JWT 를 FastAPI 는 **검증만** 한다
(provider-agnostic — CLAUDE §4.4). 비대칭(JWKS) 방식:
  JWKS = {SUPABASE_URL}/auth/v1/.well-known/jwks.json

- `get_optional_user`: 토큰 없음/무효 → None (비로그인·익명 미발급 허용 경로).
- `get_current_user`: 유효 토큰 필수 → 없거나 무효면 AuthError(401).
사용자·선호 데이터는 여기서 다루지 않는다(db/ 담당). 여기선 신원 확인만.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import jwt
from fastapi import Request
from jwt import PyJWKClient

from app.config import settings
from app.core.exceptions import AuthError

_ALGORITHMS = ["ES256", "RS256"]  # Supabase 비대칭 서명(프로젝트에 따라)
_AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthUser:
    """검증된 사용자 신원(JWT 클레임 일부)."""

    id: str  # sub — Supabase user_id (익명·정식 공통)
    is_anonymous: bool
    role: str | None = None


_jwks_client: PyJWKClient | None = None


def _client() -> PyJWKClient:
    # 키를 캐시(cache_keys)해 매 요청 네트워크 조회를 피한다.
    global _jwks_client
    if _jwks_client is None:
        if not settings.supabase_url:
            raise AuthError("Auth is not configured.")
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwks_client


def _decode(token: str) -> dict:
    # PyJWKClient 는 동기 네트워크(최초 1회) → 호출부에서 to_thread 로 감싼다.
    signing_key = _client().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        signing_key,
        algorithms=_ALGORITHMS,
        audience=_AUDIENCE,
        issuer=f"{settings.supabase_url}/auth/v1",
    )


async def verify_token(token: str) -> AuthUser:
    try:
        claims = await asyncio.to_thread(_decode, token)
    except jwt.PyJWTError as e:
        raise AuthError("Invalid or expired session.") from e
    sub = claims.get("sub")
    if not sub:
        raise AuthError("Invalid session (no subject).")
    return AuthUser(
        id=str(sub),
        is_anonymous=bool(claims.get("is_anonymous", False)),
        role=claims.get("role"),
    )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[7:].strip()
        return token or None
    return None


async def get_optional_user(request: Request) -> AuthUser | None:
    """토큰이 있으면 검증해 반환, 없거나 무효면 None(요청을 막지 않음)."""
    token = _bearer(request)
    if not token:
        return None
    try:
        return await verify_token(token)
    except AuthError:
        return None


async def get_current_user(request: Request) -> AuthUser:
    """유효 토큰 필수. 없거나 무효면 AuthError(401)."""
    token = _bearer(request)
    if not token:
        raise AuthError("Sign-in required.")
    return await verify_token(token)
