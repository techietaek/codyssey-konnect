"""JWT 검증 테스트 (Phase 2 L1a) — JWKS 네트워크 없이 EC 키로 서명·주입."""

from __future__ import annotations

import asyncio
import time
import types

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.config import settings
from app.core import auth
from app.core.exceptions import AuthError

_PRIV = ec.generate_private_key(ec.SECP256R1())
_PUB = _PRIV.public_key()
_ISS = f"{settings.supabase_url}/auth/v1"


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_PUB)


@pytest.fixture(autouse=True)
def _inject_jwks(monkeypatch):
    monkeypatch.setattr(auth, "_client", lambda: _FakeClient())


def _token(**over):
    claims = {
        "sub": "user-1",
        "aud": "authenticated",
        "iss": _ISS,
        "role": "authenticated",
        "is_anonymous": False,
        "exp": int(time.time()) + 3600,
    }
    claims.update(over)
    return jwt.encode(claims, _PRIV, algorithm="ES256")


def _req(token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return types.SimpleNamespace(headers=headers)


def test_valid_token_returns_user():
    u = asyncio.run(auth.verify_token(_token()))
    assert u.id == "user-1"
    assert u.is_anonymous is False
    assert u.role == "authenticated"


def test_anonymous_claim_parsed():
    u = asyncio.run(auth.verify_token(_token(is_anonymous=True, sub="anon-9")))
    assert u.id == "anon-9"
    assert u.is_anonymous is True


def test_expired_token_rejected():
    with pytest.raises(AuthError):
        asyncio.run(auth.verify_token(_token(exp=int(time.time()) - 10)))


def test_wrong_audience_rejected():
    with pytest.raises(AuthError):
        asyncio.run(auth.verify_token(_token(aud="other")))


def test_wrong_issuer_rejected():
    with pytest.raises(AuthError):
        asyncio.run(auth.verify_token(_token(iss="https://evil.example/auth/v1")))


def test_missing_sub_rejected():
    # sub 없는 토큰 → AuthError
    tok = jwt.encode(
        {"aud": "authenticated", "iss": _ISS, "exp": int(time.time()) + 60},
        _PRIV,
        algorithm="ES256",
    )
    with pytest.raises(AuthError):
        asyncio.run(auth.verify_token(tok))


def test_optional_user_none_without_token():
    assert asyncio.run(auth.get_optional_user(_req())) is None


def test_optional_user_none_on_invalid():
    assert asyncio.run(auth.get_optional_user(_req("garbage.token.here"))) is None


def test_optional_user_ok_with_valid():
    u = asyncio.run(auth.get_optional_user(_req(_token())))
    assert u is not None and u.id == "user-1"


def test_current_user_requires_token():
    with pytest.raises(AuthError):
        asyncio.run(auth.get_current_user(_req()))


def test_current_user_ok_with_valid():
    u = asyncio.run(auth.get_current_user(_req(_token(sub="abc"))))
    assert u.id == "abc"
