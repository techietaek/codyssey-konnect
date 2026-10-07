"""Supabase 클라이언트 (service key) — 백엔드 전용.

service(secret) key 는 RLS 를 우회하므로, cross-user 접근은 **코드에서 user_id 바인딩**
으로 막는다(검증된 JWT 의 sub 만 사용). RLS 는 publishable key 직접접근 방어선(§L1c).
키 미설정 시 SystemError(503) — 추천(비DB) 경로는 영향받지 않는다.
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings
from app.core.exceptions import SystemError


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise SystemError("Storage is not configured.")
    return create_client(settings.supabase_url, settings.supabase_secret_key)
