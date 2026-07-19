"""Consensus + scoring tests (PRD §7)."""

from __future__ import annotations

from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    Severity,
)
from app.review.consensus import Gate, build_consensus
from app.review.scoring import build_scorecard


def _f(
    *,
    agent: str = "security",
    dimension: Dimension = Dimension.SECURITY,
    category: str = "x",
    severity: Severity = Severity.HIGH,
    confidence: float = 0.9,
    file_path: str | None = "a.py",
    line: int | None = 1,
    source: FindingSource = FindingSource.DETERMINISTIC,
) -> Finding:
    return Finding(
        agent=agent,
        dimension=dimension,
        category=category,
        severity=severity,
        confidence=confidence,
        title="Title here",
        message="msg",
        file_path=file_path,
        line=line,
        source=source,
        explanation=Explanation(why="w", impact="i"),
    )


def test_empty_findings_is_not_blocking() -> None:
    result = build_consensus([])
    assert not result.blocking
    assert "clean" in result.reasoning.lower()


def test_duplicate_findings_are_merged_and_agreement_counted() -> None:
    a = _f(agent="security")
    b = _f(agent="architecture", dimension=Dimension.SECURITY)  # same key, different agent
    result = build_consensus([a, b])
    assert len(result.items) == 1
    assert result.items[0].agreement == 2


def test_high_severity_posts_and_blocks() -> None:
    result = build_consensus([_f(severity=Severity.CRITICAL, confidence=0.95)])
    assert result.items[0].gate is Gate.POST
    assert result.blocking


def test_low_confidence_info_is_suppressed() -> None:
    result = build_consensus([_f(severity=Severity.INFO, confidence=0.2, source=FindingSource.LLM)])
    assert result.items[0].gate is Gate.SUPPRESS
    assert not result.blocking


def test_security_weight_exceeds_documentation() -> None:
    sec = build_consensus([_f(dimension=Dimension.SECURITY, confidence=0.6)]).items[0]
    doc = build_consensus(
        [_f(dimension=Dimension.DOCUMENTATION, category="d", confidence=0.6)]
    ).items[0]
    assert sec.weighted_confidence > doc.weighted_confidence


def test_scorecard_drops_security_score_on_critical() -> None:
    clean = build_scorecard([])
    assert clean["security"] == 100.0
    assert clean["overall"] == 100.0
    vulnerable = build_scorecard([_f(severity=Severity.CRITICAL, confidence=1.0)])
    assert vulnerable["security"] < 100.0
    assert vulnerable["overall"] < 100.0


def test_scorecard_keys_match_db_columns() -> None:
    keys = set(build_scorecard([]))
    assert {
        "security",
        "architecture",
        "performance",
        "maintainability",
        "documentation",
        "tech_debt",
        "overall",
    } <= keys
