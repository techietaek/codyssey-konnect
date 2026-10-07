"""지식베이스 적재 스크립트 — knowledge/*.md → 청크 → 임베딩 → pgvector(vecs).

실행:  python -m app.rag.ingest
전제:  .env 의 OPENAI_API_KEY · SUPABASE_DB_URL(Postgres 직결 DSN).
멱등:  같은 id 는 upsert 로 갱신(문서 수정 후 재실행 안전).
"""

from __future__ import annotations

import asyncio

from app.rag import store
from app.rag.chunk import load_knowledge
from app.rag.embed import embed_documents


async def main() -> None:
    chunks = load_knowledge()
    if not chunks:
        print("No knowledge documents found.")
        return
    vectors = await embed_documents([c.text for c in chunks])
    records = [
        (
            c.id,
            vec,
            {"text": c.text, "doc_title": c.doc_title, "section": c.section},
        )
        for c, vec in zip(chunks, vectors, strict=True)
    ]
    n = await asyncio.to_thread(store.upsert, records)
    print(f"Ingested {n} chunks from {len({c.doc_id for c in chunks})} documents.")


if __name__ == "__main__":
    asyncio.run(main())
