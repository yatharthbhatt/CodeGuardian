"""Performance Agent (PRD §5.3).

Deterministic heuristics for common performance smells (N+1 queries, over-fetching,
blocking I/O on async paths) + LLM suggestions for caching/indexing/async opportunities.
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
    "You are a performance engineer. Review the diff for N+1 queries, unnecessary work in "
    "hot paths, missing caching/indexing, blocking I/O on async paths, and inefficient data "
    "structures. Only report issues justified by the diff."
)

_RULES: list[DeterministicRule] = [
    DeterministicRule(
        category="select-star",
        severity=Severity.LOW,
        pattern=re.compile(r"(?i)select\s+\*\s+from"),
        title="SELECT * over-fetches columns",
        why="Fetching all columns wastes I/O and memory and breaks on schema changes.",
        impact="Higher latency and bandwidth than necessary.",
        alternative="Select only the columns you need.",
    ),
    DeterministicRule(
        category="blocking-io-in-async",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"\b(requests\.(get|post|put|delete)|time\.sleep|urllib\.request)\b"),
        title="Blocking call likely on an async/hot path",
        why="Synchronous network/sleep calls block the event loop or a worker thread.",
        impact="Throughput collapse under concurrency.",
        alternative="Use an async client (httpx/aiohttp) or offload to a thread pool.",
        languages=frozenset({"python"}),
    ),
    DeterministicRule(
        category="unbounded-readall",
        severity=Severity.LOW,
        pattern=re.compile(r"\.read\(\)\s*$|\.readlines\(\)"),
        title="Reading an entire stream into memory",
        why="Loading whole files/streams can exhaust memory on large inputs.",
        impact="Memory spikes / OOM on large inputs.",
        alternative="Stream/iterate in chunks.",
    ),
]

# ORM/DB call signatures that, inside a loop, suggest an N+1 query pattern.
_DB_CALL = re.compile(r"\.(query|filter|get|all|execute|fetch\w*|find|objects)\b|session\.")
_LOOP = re.compile(r"^\s*(for|while)\b")


class PerformanceAgent:
    name = "performance"
    dimension = Dimension.PERFORMANCE

    async def run(self, ctx: AgentContext) -> list[Finding]:
        findings = scan_rules(ctx.diff, _RULES, agent=self.name, dimension=self.dimension)
        findings.extend(self._detect_n_plus_one(ctx))
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List performance issues and optimizations in this diff.",
            )
        )
        return findings

    def _detect_n_plus_one(self, ctx: AgentContext) -> list[Finding]:
        out: list[Finding] = []
        for file in ctx.diff.files:
            lines = file.added
            for i, line in enumerate(lines):
                if not _LOOP.search(line.text):
                    continue
                # Look a short window ahead for a DB call inside the loop body.
                window = lines[i + 1 : i + 12]
                hit = next((ln for ln in window if _DB_CALL.search(ln.text)), None)
                if hit is None:
                    continue
                out.append(
                    Finding(
                        agent=self.name,
                        dimension=self.dimension,
                        category="n-plus-one-query",
                        severity=Severity.MEDIUM,
                        confidence=0.6,
                        title="Possible N+1 query inside a loop",
                        message=(
                            f"A database call at {file.path}:{hit.new_line} runs inside a "
                            f"loop starting at line {line.new_line}."
                        ),
                        file_path=file.path,
                        line=hit.new_line,
                        source=FindingSource.DETERMINISTIC,
                        explanation=Explanation(
                            why="Querying per-iteration multiplies round-trips (N+1).",
                            impact="Latency grows linearly with collection size.",
                            alternative="Batch/prefetch (join, IN query, select_related).",
                            complexity="medium",
                        ),
                    )
                )
                break  # one N+1 hint per file is enough
        return out
