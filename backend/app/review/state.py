"""Shared review state for the LangGraph orchestrator (PRD §6).

``ReviewState`` is the typed, append-only-ish state that flows through the graph.
``findings`` uses an ``operator.add`` reducer so parallel agent nodes can each append
their findings without clobbering one another (LangGraph fan-in).
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app.domain.findings import Finding
from app.review.diff import NormalizedDiff


@dataclass(frozen=True)
class PRMeta:
    tenant_id: str
    repo_full_name: str
    number: int
    title: str
    body: str
    author: str
    head_sha: str
    base_sha: str

    def as_untrusted_context(self) -> str:
        """PR text the model may see — treated as untrusted (wrapped by prompting)."""
        return f"PR #{self.number}: {self.title}\n\n{self.body}"


class ReviewState(TypedDict, total=False):
    pr: PRMeta
    diff: NormalizedDiff
    findings: Annotated[list[Finding], operator.add]
    # Per-agent errors so one failing agent doesn't fail the whole review (rule #9).
    errors: Annotated[list[dict[str, str]], operator.add]
    consensus: dict[str, Any]
    risk: dict[str, float]
