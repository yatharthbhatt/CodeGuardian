"""Memory context passed to agents (PRD §11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.memory.graph.base import RegressionInfo


@dataclass
class SimilarFinding:
    title: str
    category: str
    score: float
    file_path: str | None = None


@dataclass
class MemoryContext:
    """Everything repository memory contributes to a single review."""

    blast_radius: list[str] = field(default_factory=list)
    regression: list[RegressionInfo] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    similar_past_findings: list[SimilarFinding] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.blast_radius or self.regression or self.cycles or self.similar_past_findings
        )

    def summary(self, *, max_items: int = 5) -> str:
        """A short, TRUSTED summary to enrich agent LLM prompts (our own derived facts)."""
        parts: list[str] = []
        if self.blast_radius:
            parts.append(
                f"This change may impact {len(self.blast_radius)} downstream file(s): "
                + ", ".join(self.blast_radius[:max_items])
            )
        risky = [r for r in self.regression if r.past_bug_count > 0]
        if risky:
            parts.append(
                "Files with prior bug history: "
                + ", ".join(f"{r.file_path} ({r.past_bug_count})" for r in risky[:max_items])
            )
        if self.cycles:
            parts.append(f"{len(self.cycles)} dependency cycle(s) touch this change.")
        if self.similar_past_findings:
            parts.append(
                "Similar past findings: "
                + "; ".join(s.title for s in self.similar_past_findings[:max_items])
            )
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blast_radius": self.blast_radius,
            "regression": [
                {"file": r.file_path, "past_bugs": r.past_bug_count, "last_bug_pr": r.last_bug_pr}
                for r in self.regression
            ],
            "cycles": self.cycles,
            "similar_past_findings": [
                {"title": s.title, "category": s.category, "score": round(s.score, 3)}
                for s in self.similar_past_findings
            ],
        }
