"""지식문서(markdown) → 청크. `## ` 섹션 단위로 쪼개고 문서 제목을 맥락으로 붙인다.

청크 경계를 섹션(heading)으로 두면 검색 근거가 "어느 문서의 어느 섹션"인지 명확해져
citation(투명 공개)과 범위 밖 refuse 판정이 쉬워진다.
"""

from __future__ import annotations

from pathlib import Path

from app.models.rag import KbChunk

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def chunk_markdown(text: str, doc_id: str) -> list[KbChunk]:
    """md 본문 → 섹션별 KbChunk. 첫 `# ` 를 문서 제목으로, `## ` 마다 새 청크."""
    lines = text.splitlines()
    doc_title = doc_id
    chunks: list[KbChunk] = []
    section = ""
    body: list[str] = []
    idx = 0

    def flush() -> None:
        nonlocal idx, body
        content = "\n".join(body).strip()
        if section and content:
            chunks.append(
                KbChunk(
                    id=f"{doc_id}#{idx}",
                    text=f"{section}\n{content}",
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section=section,
                )
            )
            idx += 1
        body = []

    for line in lines:
        if line.startswith("# ") and not line.startswith("## "):
            doc_title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            section = line[3:].strip()
        else:
            body.append(line)
    flush()
    return chunks


def load_knowledge() -> list[KbChunk]:
    """knowledge/*.md 전부 → 청크 리스트(파일명 stem = doc_id)."""
    chunks: list[KbChunk] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), path.stem))
    return chunks
