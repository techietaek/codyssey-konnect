"""RAG 결정론 로직 — 청크 분할 + 근거 판정(임계치·refuse). (DB·LLM 불필요)"""

from app.rag.chunk import chunk_markdown, load_knowledge
from app.rag.retrieve import SIM_THRESHOLD, filter_grounded

_MD = """# Doc Title

intro line (헤딩 없는 선두는 청크 아님)

## Section A
body a1
body a2

## Section B
body b1
"""


def test_chunk_splits_by_section_with_title():
    chunks = chunk_markdown(_MD, "doc")
    assert [c.section for c in chunks] == ["Section A", "Section B"]
    assert all(c.doc_title == "Doc Title" for c in chunks)
    assert chunks[0].id == "doc#0" and chunks[1].id == "doc#1"
    assert "body a1" in chunks[0].text and chunks[0].text.startswith("Section A")


def test_chunk_ignores_preamble_without_heading():
    # 첫 '## ' 이전 선두 문단은 청크로 만들지 않는다(섹션 근거 단위 유지).
    chunks = chunk_markdown(_MD, "doc")
    assert all("intro line" not in c.text for c in chunks)


def test_load_knowledge_returns_chunks():
    chunks = load_knowledge()
    assert len(chunks) > 0
    assert any(c.doc_id == "transport" for c in chunks)


def _meta(section):
    return {"text": f"{section} text", "doc_title": "D", "section": section}


def test_filter_grounded_keeps_above_threshold_sorted():
    scored = [
        (_meta("low"), SIM_THRESHOLD - 0.1),
        (_meta("mid"), SIM_THRESHOLD + 0.1),
        (_meta("high"), SIM_THRESHOLD + 0.3),
    ]
    kept = filter_grounded(scored, SIM_THRESHOLD, 4)
    assert [m["section"] for m, _ in kept] == [
        "high",
        "mid",
    ]  # 임계치 미만 제외·내림차순


def test_filter_grounded_empty_when_all_below():
    scored = [(_meta("a"), 0.1), (_meta("b"), 0.2)]
    assert filter_grounded(scored, SIM_THRESHOLD, 4) == []  # → refuse 경로


def test_filter_grounded_caps_top_k():
    scored = [(_meta(str(i)), SIM_THRESHOLD + 0.1) for i in range(6)]
    assert len(filter_grounded(scored, SIM_THRESHOLD, 4)) == 4  # 상위 K 제한
