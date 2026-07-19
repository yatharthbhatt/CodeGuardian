"""Consensus Engine (PRD §7).

Not majority voting — **weighted confidence**. Findings are deduped by location+category;
agreement across agents boosts confidence; per-dimension weights reflect how much we trust
each agent. Confidence gating then decides whether each finding is posted, collapsed, or
suppressed (noise control).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.domain.findings import Dimension, Finding, FindingSource, Severity

# How much each dimension's verdict counts (PRD §7 example weights).
_DIMENSION_WEIGHT: dict[Dimension, float] = {
    Dimension.SECURITY: 1.30,
    Dimension.CORRECTNESS: 1.20,
    Dimension.ARCHITECTURE: 1.00,
    Dimension.DEVOPS: 1.00,
    Dimension.PERFORMANCE: 0.90,
    Dimension.TESTING: 0.90,
    Dimension.ACCESSIBILITY: 0.80,
    Dimension.DOCUMENTATION: 0.70,
}

# Deterministic findings are trusted more than model-only ones.
_SOURCE_MULTIPLIER: dict[FindingSource, float] = {
    FindingSource.DETERMINISTIC: 1.00,
    FindingSource.HYBRID: 0.95,
    FindingSource.LLM: 0.85,
}

_POST_THRESHOLD = 0.75
_COLLAPSE_THRESHOLD = 0.40


class Gate(StrEnum):
    POST = "post"  # inline/blocking comment
    COLLAPSE = "collapse"  # low-priority "consider" note
    SUPPRESS = "suppress"  # kept in dashboard, off the PR (anti-fatigue)


@dataclass
class ConsensusItem:
    finding: Finding
    weighted_confidence: float
    agreement: int
    gate: Gate


@dataclass
class ConsensusResult:
    items: list[ConsensusItem]
    reasoning: str
    blocking: bool

    @property
    def posted(self) -> list[ConsensusItem]:
        return [i for i in self.items if i.gate is Gate.POST]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning": self.reasoning,
            "blocking": self.blocking,
            "counts": {gate.value: sum(1 for i in self.items if i.gate is gate) for gate in Gate},
            "items": [
                {
                    "title": i.finding.title,
                    "dimension": i.finding.dimension.value,
                    "severity": i.finding.severity.value,
                    "weighted_confidence": round(i.weighted_confidence, 3),
                    "agreement": i.agreement,
                    "gate": i.gate.value,
                    "file_path": i.finding.file_path,
                    "line": i.finding.line,
                }
                for i in self.items
            ],
        }


def _gate_for(severity: Severity, weighted: float) -> Gate:
    # High-impact issues post at a lower confidence bar.
    if severity in (Severity.CRITICAL, Severity.HIGH) and weighted >= 0.50:
        return Gate.POST
    if weighted >= _POST_THRESHOLD:
        return Gate.POST
    if weighted >= _COLLAPSE_THRESHOLD:
        return Gate.COLLAPSE
    return Gate.SUPPRESS


def build_consensus(
    findings: list[Finding], adjustments: dict[str, float] | None = None
) -> ConsensusResult:
    """Dedupe, weight, and gate findings into a consensus verdict.

    ``adjustments`` are per-category confidence multipliers learned from developer feedback
    (Golden Path, PRD §8.12): categories a team routinely rejects are down-weighted so they
    get suppressed sooner.
    """
    adjustments = adjustments or {}
    # Group by identity so multiple agents flagging the same spot reinforce each other.
    groups: dict[tuple[str, str, str, int], list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.dedupe_key(), []).append(f)

    items: list[ConsensusItem] = []
    for group in groups.values():
        # Keep the most severe / most confident representative.
        rep = max(group, key=lambda g: (g.severity.weight, g.confidence))
        agreement = len({g.agent for g in group})
        weight = _DIMENSION_WEIGHT.get(rep.dimension, 1.0)
        source_mult = _SOURCE_MULTIPLIER.get(rep.source, 0.85)
        agreement_boost = 1.0 + 0.05 * (agreement - 1)
        feedback_mult = adjustments.get(rep.category, 1.0)
        weighted = min(1.0, rep.confidence * weight * source_mult * agreement_boost * feedback_mult)
        items.append(
            ConsensusItem(
                finding=rep,
                weighted_confidence=weighted,
                agreement=agreement,
                gate=_gate_for(rep.severity, weighted),
            )
        )

    items.sort(key=lambda i: (i.finding.severity.weight, i.weighted_confidence), reverse=True)
    blocking = any(
        i.gate is Gate.POST and i.finding.severity in (Severity.CRITICAL, Severity.HIGH)
        for i in items
    )
    return ConsensusResult(items=items, reasoning=_reason(items, blocking), blocking=blocking)


def _reason(items: list[ConsensusItem], blocking: bool) -> str:
    if not items:
        return "No issues found across agents; PR looks clean."
    posted = sum(1 for i in items if i.gate is Gate.POST)
    per_dim: dict[str, int] = {}
    for i in items:
        per_dim[i.finding.dimension.value] = per_dim.get(i.finding.dimension.value, 0) + 1
    dims = ", ".join(f"{k}:{v}" for k, v in sorted(per_dim.items()))
    verdict = "Requesting changes" if blocking else "Commenting"
    return (
        f"{verdict}. {posted} finding(s) met the confidence bar to post "
        f"(of {len(items)} deduped). By dimension — {dims}. "
        "Weights favor security/correctness and deterministic detections."
    )
