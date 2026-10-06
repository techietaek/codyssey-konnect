"""Trace 로깅 베이스 (NFR-08 · PoC 증빙).

Agent 다단계 동작(조회→판정→분기→구성→설명)을 재현 가능하게 기록하기 위한
최소 골격. Phase 0 에서는 trace_id 발급 + 단계 로깅만 둔다.
LangChain callbacks/LangSmith 연동은 이후 단계에서 이 베이스 위에 얹는다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("konnect.trace")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Trace:
    """한 요청의 다단계 동작을 모으는 컨테이너."""

    trace_id: str = field(default_factory=new_trace_id)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def step(self, name: str, **data: Any) -> None:
        """한 단계(structure/fetch/judge/compose/explain 등)를 기록."""
        entry = {"step": name, **data}
        self.steps.append(entry)
        logger.info("[%s] %s %s", self.trace_id, name, data or "")
