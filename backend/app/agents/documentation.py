"""Documentation Agent (PRD §5.4).

Deterministic checks for undocumented public API surface + LLM suggestions for README,
examples, and changelog entries.
"""

from __future__ import annotations

import re

from app.agents.base import AgentContext, run_llm_enrichment
from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    Severity,
)

_SYSTEM = (
    "You are a documentation specialist. Identify missing or unclear documentation: "
    "public functions/classes without docstrings, missing README/usage, absent examples, "
    "and changelog gaps. Be specific about what to add."
)

# Public (non-underscore) Python def/class added lines.
_PUBLIC_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(?!_)(\w+)|^\s*class\s+(?!_)(\w+)")
_DOCSTRING = re.compile(r'^\s*[ru]?["\']{3}')


class DocumentationAgent:
    name = "documentation"
    dimension = Dimension.DOCUMENTATION

    async def run(self, ctx: AgentContext) -> list[Finding]:
        findings = self._missing_docstrings(ctx)
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List documentation gaps introduced by this diff.",
            )
        )
        return findings

    def _missing_docstrings(self, ctx: AgentContext) -> list[Finding]:
        out: list[Finding] = []
        for file in ctx.diff.files:
            if file.language != "python":
                continue
            lines = file.added
            for i, line in enumerate(lines):
                if not _PUBLIC_DEF.search(line.text):
                    continue
                # Look at the next non-blank added line for a docstring.
                nxt = next((ln for ln in lines[i + 1 : i + 4] if ln.text.strip()), None)
                if nxt is not None and _DOCSTRING.search(nxt.text):
                    continue
                out.append(
                    Finding(
                        agent=self.name,
                        dimension=self.dimension,
                        category="missing-docstring",
                        severity=Severity.LOW,
                        confidence=0.7,
                        title="Public definition lacks a docstring",
                        message=(
                            f"{file.path}:{line.new_line} defines public API without a docstring."
                        ),
                        file_path=file.path,
                        line=line.new_line,
                        source=FindingSource.DETERMINISTIC,
                        explanation=Explanation(
                            why="Undocumented public API slows onboarding and invites misuse.",
                            impact="Higher support burden and integration errors.",
                            alternative="Add a concise docstring: purpose, args, returns.",
                            complexity="low",
                        ),
                    )
                )
        return out
