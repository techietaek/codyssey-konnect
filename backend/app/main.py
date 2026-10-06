"""FastAPI 엔트리 (Phase 0 Walking Skeleton).

- GET /health            : 라이브니스
- POST /api/recommend    : 즉시 추천(A) 스텁
- CORS                   : .env CORS_ALLOW_ORIGINS
- 공통 예외 → Envelope(ok=False) 로 변환 (FR-C7: 시스템 예외 vs 정상결과 분리)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.recommend import router as recommend_router
from app.config import settings
from app.core.exceptions import KonnectError
from app.core.trace import new_trace_id
from app.models.envelope import Envelope

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("konnect")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """핵심 키 '존재 여부'만 확인·로깅(값 미출력, NFR-04)."""
    required = ["openai_api_key", "supabase_url", "data_go_kr_service_key"]
    missing = settings.missing_keys(required)
    if missing:
        logger.warning("env: missing keys -> %s", ", ".join(missing))
    else:
        logger.info("env: core keys present (%d checked)", len(required))
    yield


app = FastAPI(title="KONNECT API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommend_router)


@app.exception_handler(KonnectError)
async def _konnect_error_handler(request: Request, exc: KonnectError) -> JSONResponse:
    env = Envelope.failure(
        code=exc.code, message=exc.user_message, trace_id=new_trace_id()
    )
    return JSONResponse(status_code=exc.http_status, content=env.model_dump())


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    env = Envelope.failure(
        code="validation_error",
        message="Please check your input and try again.",
        trace_id=new_trace_id(),
    )
    return JSONResponse(status_code=422, content=env.model_dump())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
