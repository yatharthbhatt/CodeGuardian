"""Architecture Agent (PRD §5.2).

Deterministic heuristics for structural smells + LLM suggestions for SOLID/Clean
Architecture/DDD. Deep graph-based analysis (circular deps, blast radius) arrives in
Phase 3 with the Neo4j knowledge graph.
"""

from __future__ import annotations

import re

from app.agents.base import (
    AgentContext,
    DeterministicRule,
    run_llm_enrichment,
    scan_rules,
)
from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    Severity,
)

_SYSTEM = (
    "You are a principal software architect. Review the diff for SOLID violations, poor "
    "modular boundaries, tight coupling, missing abstractions, and design-pattern "
    "opportunities. Be concrete and reference the changed code."
)

_RULES: list[DeterministicRule] = [
    DeterministicRule(
        category="wildcard-import",
        severity=Severity.LOW,
        pattern=re.compile(r"^\s*from\s+[\w.]+\s+import\s+\*"),
        title="Wildcard import",
        why="Wildcard imports pollute the namespace and hide dependencies.",
        impact="Reduced readability and higher coupling.",
        alternative="Import explicit names.",
        languages=frozenset({"python"}),
    ),
    DeterministicRule(
        category="broad-except",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"except\s*(Exception)?\s*:"),
        title="Overly broad exception handler",
        why="Catching everything hides bugs and complicates control flow.",
        impact="Silent failures and poor error boundaries.",
        alternative="Catch specific exceptions and handle them intentionally.",
        languages=frozenset({"python"}),
    ),
    DeterministicRule(
        category="global-mutable-state",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"^\s*global\s+\w+"),
        title="Use of global mutable state",
        why="Globals create hidden coupling and hurt testability/thread-safety.",
        impact="Fragile, hard-to-reason-about modules.",
        alternative="Pass dependencies explicitly or use a scoped container.",
        languages=frozenset({"python"}),
    ),
]

# Function bodies longer than this many added lines are flagged as a complexity smell.
_LONG_FUNCTION_LINES = 60
_FUNC_DEF = re.compile(r"^\s*(?:async\s+)?def\s+\w+|^\s*function\s+\w+|=>\s*\{?$")


class ArchitectureAgent:
    name = "architecture"
    dimension = Dimension.ARCHITECTURE

    async def run(self, ctx: AgentContext) -> list[Finding]:
        findings = scan_rules(ctx.diff, _RULES, agent=self.name, dimension=self.dimension)
        findings.extend(self._long_functions(ctx))
        findings.extend(self._circular_dependencies(ctx))
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List architectural issues and refactoring opportunities in this diff.",
            )
        )
        return findings

    def _circular_dependencies(self, ctx: AgentContext) -> list[Finding]:
        """Report dependency cycles (from the memory graph's DEPENDS_ON edges)."""
        if ctx.memory is None:
            return []
        touched = {f.path for f in ctx.diff.files}
        out: list[Finding] = []
        for cycle in ctx.memory.cycles:
            anchor = next((p for p in cycle if p in touched), cycle[0])
            out.append(
                Finding(
                    agent=self.name,
                    dimension=self.dimension,
                    category="circular-dependency",
                    severity=Severity.MEDIUM,
                    confidence=0.85,
                    title="Circular dependency between modules",
                    message="Dependency cycle: " + " -> ".join(cycle) + f" -> {cycle[0]}.",
                    file_path=anchor,
                    source=FindingSource.DETERMINISTIC,
                    explanation=Explanation(
                        why="Cyclic imports couple modules tightly and cause fragile init order.",
                        impact="Hard-to-test, hard-to-change modules; import errors.",
                        alternative="Break the cycle via an interface/DI or extract shared code.",
                        complexity="medium",
                    ),
                )
            )
        return out

    def _long_functions(self, ctx: AgentContext) -> list[Finding]:
        out: list[Finding] = []
        for file in ctx.diff.files:
            if len(file.added) <= _LONG_FUNCTION_LINES:
                continue
            if any(_FUNC_DEF.search(line.text) for line in file.added):
                first = file.added[0]
                out.append(
                    Finding(
                        agent=self.name,
                        dimension=self.dimension,
                        category="large-change-surface",
                        severity=Severity.LOW,
                        confidence=0.6,
                        title="Large function/file change — consider decomposition",
                        message=(
                            f"{file.path} adds {len(file.added)} lines containing function "
                            "definitions; consider smaller, single-responsibility units."
                        ),
                        file_path=file.path,
                        line=first.new_line,
                        source=FindingSource.DETERMINISTIC,
                        explanation=Explanation(
                            why="Large units tend to violate single-responsibility "
                            "and are hard to test.",
                            impact="Lower maintainability and higher defect rate.",
                            alternative="Extract cohesive helpers; separate concerns.",
                            complexity="medium",
                        ),
                    )
                )
        return out
