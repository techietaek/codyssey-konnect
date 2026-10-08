"""환경변수 로딩·검증 (pydantic-settings).

규칙(CLAUDE.md §5·NFR-04): 비밀값은 .env 에서만 주입, 값은 절대 출력하지 않는다.
startup 시 '키 존재 여부'(이름만)만 확인·로깅한다.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py → parents[2] = code/  (리포 루트의 .env 를 가리킨다)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──
    app_env: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_allow_origins: str = "http://localhost:5500,http://127.0.0.1:5500"
    api_base_url: str = "http://localhost:8000"

    # ── Agent ──
    # 전체 agentic while-loop(§6) 사용 여부. off 면 기존 단일 라우팅(chat_agent)이 fallback.
    agent_loop: bool = False

    # ── OpenAI ──
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # ── Supabase ──
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    # vecs(pgvector) 직결용 Postgres DSN. REST(supabase-py)로는 벡터 upsert/query 불가 →
    # RAG 적재·검색에만 사용. 미설정 시 RAG 경로만 503(추천·세션 경로 영향 없음).
    supabase_db_url: str = ""

    # ── Maps / Movement ──
    naver_map_client_id: str = ""
    tmap_api_key: str = ""
    google_places_api_key: str = ""

    # ── Official data APIs ──
    data_go_kr_service_key: str = ""
    seoul_openapi_key: str = ""
    kopis_api_key: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    def missing_keys(self, names: list[str]) -> list[str]:
        """주어진 설정명 중 값이 비어있는 것의 '이름만' 반환(값 미출력)."""
        return [n for n in names if not getattr(self, n, "")]


settings = Settings()
