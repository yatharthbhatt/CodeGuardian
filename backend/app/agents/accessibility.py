"""Accessibility Agent (PRD §5.7).

Deterministic WCAG-oriented checks on frontend markup/JSX + LLM suggestions. Only runs
against frontend files (the triage router won't even schedule it otherwise).
"""

from __future__ import annotations

import re

from app.agents.base import (
    AgentContext,
    DeterministicRule,
    run_llm_enrichment,
    scan_rules,
)
from app.domain.findings import Dimension, Finding, Severity

_SYSTEM = (
    "You are an accessibility (a11y) specialist. Review UI code for WCAG 2.2 issues: missing "
    "alt text, non-semantic interactive elements, keyboard traps, ARIA misuse, and contrast. "
    "Only report issues in the diff."
)

_FRONTEND = frozenset({"javascript", "typescript", "html"})

_RULES: list[DeterministicRule] = [
    DeterministicRule(
        category="img-missing-alt",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"<img\b(?![^>]*\balt\s*=)[^>]*>"),
        title="<img> without alt text",
        why="Screen readers cannot describe images that lack alt text.",
        impact="Content is inaccessible to blind/low-vision users (WCAG 1.1.1).",
        alternative='Add descriptive alt text, or alt="" for decorative images.',
        languages=_FRONTEND,
    ),
    DeterministicRule(
        category="non-semantic-interactive",
        severity=Severity.LOW,
        pattern=re.compile(r"<(div|span)\b[^>]*\bonClick\b"),
        title="Click handler on a non-interactive element",
        why="div/span with onClick aren't keyboard-focusable or announced as controls.",
        impact="Keyboard/screen-reader users cannot activate it (WCAG 2.1.1).",
        alternative="Use a <button>, or add role and keyboard handlers.",
        languages=_FRONTEND,
    ),
    DeterministicRule(
        category="positive-tabindex",
        severity=Severity.LOW,
        pattern=re.compile(r'tabindex\s*=\s*["\']?[1-9]'),
        title="Positive tabindex disrupts focus order",
        why="Positive tabindex overrides natural focus order and confuses navigation.",
        impact="Unpredictable keyboard navigation (WCAG 2.4.3).",
        alternative="Use tabindex=0 / -1 and rely on DOM order.",
        languages=_FRONTEND,
    ),
]


class AccessibilityAgent:
    name = "accessibility"
    dimension = Dimension.ACCESSIBILITY

    async def run(self, ctx: AgentContext) -> list[Finding]:
        findings = scan_rules(ctx.diff, _RULES, agent=self.name, dimension=self.dimension)
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List accessibility issues in this diff.",
            )
        )
        return findings
