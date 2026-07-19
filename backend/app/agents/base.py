"""Agent framework: deterministic rule engine + safe LLM enrichment.

Every agent is **deterministic-first** (PRD rule #8): fast, trustworthy regex/AST-style
rules run first and produce high-confidence findings; an optional LLM pass then *adds*
lower-trust suggestions, with its output strictly validated and constrained to files that
actually appear in the diff (so the model cannot invent or redirect findings).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import ValidationError

from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    LLMFinding,
    Severity,
)
from app.llm.base import BudgetExceededError, TokenBudget
from app.llm.prompting import build_review_request
from app.llm.router import LLMRouter
from app.memory.types import MemoryContext
from app.review.diff import NormalizedDiff
from app.review.state import PRMeta

log = logging.getLogger("codeguardian.agents")


@dataclass
class AgentContext:
    pr: PRMeta
    diff: NormalizedDiff
    router: LLMRouter | None = None
    budget: TokenBudget | None = None
    use_llm: bool = True
    memory: MemoryContext | None = None


class Agent(Protocol):
    name: str
    dimension: Dimension

    async def run(self, ctx: AgentContext) -> list[Finding]: ...


@dataclass(frozen=True)
class DeterministicRule:
    """A single scanner rule applied line-by-line to added code."""

    category: str
    severity: Severity
    pattern: re.Pattern[str]
    title: str
    why: str
    impact: str
    alternative: str = ""
    cwe: str | None = None
    confidence: float = 0.9
    languages: frozenset[str] = field(default_factory=frozenset)  # empty = all


def scan_rules(
    diff: NormalizedDiff, rules: list[DeterministicRule], *, agent: str, dimension: Dimension
) -> list[Finding]:
    """Run deterministic rules against every added line in the diff."""
    findings: list[Finding] = []
    for file in diff.files:
        for line in file.added:
            for rule in rules:
                if rule.languages and file.language not in rule.languages:
                    continue
                if rule.pattern.search(line.text):
                    findings.append(
                        Finding(
                            agent=agent,
                            dimension=dimension,
                            category=rule.category,
                            severity=rule.severity,
                            confidence=rule.confidence,
                            title=rule.title,
                            message=f"{rule.title} at {file.path}:{line.new_line}.",
                            file_path=file.path,
                            line=line.new_line,
                            cwe=rule.cwe,
                            source=FindingSource.DETERMINISTIC,
                            explanation=Explanation(
                                why=rule.why,
                                impact=rule.impact,
                                alternative=rule.alternative,
                                complexity="low",
                            ),
                        )
                    )
    return findings


def _parse_llm_findings(
    text: str, *, agent: str, dimension: Dimension, valid_paths: set[str]
) -> list[Finding]:
    """Validate + constrain LLM output (PRD rule #3). Never raises."""
    findings: list[Finding] = []
    try:
        data = json.loads(text)
        raw_items = data.get("findings", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, AttributeError):
        log.warning("llm output was not valid json", extra={"agent": agent})
        return []
    if not isinstance(raw_items, list):
        return []

    for item in raw_items[:50]:  # cap the number of LLM findings
        try:
            lf = LLMFinding.model_validate(item)
        except ValidationError:
            continue
        # Constrain to files actually in the diff — the model cannot redirect elsewhere.
        if lf.file_path is not None and lf.file_path not in valid_paths:
            lf.file_path = None
            lf.line = None
        findings.append(
            Finding(
                agent=agent,
                dimension=dimension,
                category=lf.category,
                severity=lf.severity,
                confidence=min(lf.confidence, 0.9),  # LLM-only claims capped below 1.0
                title=lf.title,
                message=lf.message,
                file_path=lf.file_path,
                line=lf.line,
                source=FindingSource.LLM,
                explanation=Explanation(
                    why=lf.why, impact=lf.impact, alternative=lf.alternative, complexity="unknown"
                ),
            )
        )
    return findings


async def run_llm_enrichment(
    ctx: AgentContext, *, agent: str, dimension: Dimension, system: str, instruction: str
) -> list[Finding]:
    """Optional LLM pass. Safe by construction: wrapped untrusted input, validated output.

    Returns [] on any error/budget exhaustion so it can never break the deterministic
    review (graceful degradation, rule #9).
    """
    if not ctx.use_llm or ctx.router is None or ctx.budget is None:
        return []
    content = ctx.pr.as_untrusted_context() + "\n\nDIFF:\n" + _diff_snippet(ctx.diff)
    # RAG: enrich the (trusted) instruction with repository memory — our own derived facts,
    # never mixed into the untrusted block.
    if ctx.memory is not None and not ctx.memory.is_empty():
        instruction = (
            f"{instruction}\n\nRepository memory (trusted context): {ctx.memory.summary()}"
        )
    request = build_review_request(
        agent_system=system, untrusted_content=content, task_instruction=instruction
    )
    try:
        resp = await ctx.router.complete(
            request, budget=ctx.budget, agent=agent, tenant=ctx.pr.tenant_id
        )
    except BudgetExceededError:
        log.info("llm enrichment skipped: budget exhausted", extra={"agent": agent})
        return []
    except Exception:
        log.exception("llm enrichment failed", extra={"agent": agent})
        return []
    valid_paths = {f.path for f in ctx.diff.files}
    return _parse_llm_findings(resp.text, agent=agent, dimension=dimension, valid_paths=valid_paths)


def _diff_snippet(diff: NormalizedDiff, *, max_files: int = 40) -> str:
    parts: list[str] = []
    for file in diff.files[:max_files]:
        parts.append(f"--- {file.path} ({file.language}) ---")
        for line in file.added:
            parts.append(f"{line.new_line}: {line.text}")
    return "\n".join(parts)
