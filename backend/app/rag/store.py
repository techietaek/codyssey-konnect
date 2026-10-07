"""Supabase pgvector 컬렉션(vecs) — 적재·검색 (CLAUDE §2·§4.5).

vecs 는 REST(supabase-py)로는 못 하는 벡터 upsert/query 를 Postgres 직결로 수행한다.
동기 라이브러리라 FastAPI 경로에서는 `asyncio.to_thread` 로 감싸 호출한다.
DSN(`supabase_db_url`) 미설정 시 SystemError → RAG 경로만 503(추천·세션 무영향).
"""

from __future__ import annotations

from typing import Any

import vecs

from app.config import settings
from app.core.exceptions import SystemError
from app.rag.embed import EMBED_DIM

COLLECTION = "konnect_knowledge"


def _normalized_dsn(dsn: str) -> str:
    """드라이버를 psycopg2 로 고정.

    vecs 는 psycopg2-binary 를 설치하지만, SQLAlchemy 2.1+ 는 bare `postgresql://` 를
    psycopg(v3) 드라이버로 해석한다(미설치 → ModuleNotFoundError). 명시 드라이버가 없을 때만
    `+psycopg2` 를 주입해 설치된 드라이버를 쓰게 한다(이미 `+driver` 가 있으면 존중).
    """
    for prefix in ("postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+psycopg2://" + dsn[len(prefix) :]
    return dsn


def _collection() -> Any:
    if not settings.supabase_db_url:
        raise SystemError("Knowledge base is not configured.")
    client = vecs.create_client(_normalized_dsn(settings.supabase_db_url))
    return client.get_or_create_collection(name=COLLECTION, dimension=EMBED_DIM)


def upsert(records: list[tuple[str, list[float], dict[str, Any]]]) -> int:
    """(id, vector, metadata) 레코드 upsert 후 ANN 인덱스 생성. 적재 건수 반환."""
    col = _collection()
    col.upsert(records=records)
    col.create_index()
    return len(records)


def query(vector: list[float], limit: int) -> list[tuple[str, float, dict[str, Any]]]:
    """질의 벡터로 유사도 검색 → (id, cosine_distance, metadata) 리스트(가까운 순)."""
    col = _collection()
    return col.query(
        data=vector,
        limit=limit,
        include_value=True,  # cosine_distance 값 포함(근거 판정 임계치용)
        include_metadata=True,
    )
