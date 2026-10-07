"""OpenAI Embeddings 래퍼 (text-embedding-3-small, 1536차원).

적재(문서)·질의(질문)가 같은 모델/차원을 쓰도록 단일 지점으로 둔다.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.config import settings

EMBED_DIM = 1536  # text-embedding-3-small


@lru_cache(maxsize=1)
def _embedder() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


async def embed_documents(texts: list[str]) -> list[list[float]]:
    return await _embedder().aembed_documents(texts)


async def embed_query(text: str) -> list[float]:
    return await _embedder().aembed_query(text)
