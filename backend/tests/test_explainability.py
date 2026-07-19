"""Explainability enforcement (PRD §8.5) — every finding is fully explained."""

from __future__ import annotations

from app.domain.explainability import enforce_explainability
from app.domain.findings import Dimension, Explanation, Finding, FindingSource, Severity
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.review.graph import run_review

from tests.conftest import diff_from_added, make_pr


def _bare_finding(dimension: Dimension = Dimension.SECURITY, cwe: str | None = "CWE-89") -> Finding:
    return Finding(
        agent="security",
        dimension=dimension,
        category="x",
        severity=Severity.HIGH,
        confidence=0.9,
        title="A finding",
        message="msg",
        cwe=cwe,
        source=FindingSource.DETERMINISTIC,
        explanation=Explanation(why="w", impact="i"),  # no alternative/references
    )


def test_enforce_fills_alternative_and_references() -> None:
    f = _bare_finding()
    enforce_explainability([f])
    assert f.explanation.alternative  # filled
    assert any("cwe.mitre.org" in r for r in f.explanation.references)  # CWE link
    assert any("owasp.org" in r for r in f.explanation.references)  # dimension ref


def test_every_dimension_gets_a_reference() -> None:
    findings = [_bare_finding(dimension=d, cwe=None) for d in Dimension]
    enforce_explainability(findings)
    assert all(f.explanation.references for f in findings)


async def test_all_findings_from_review_are_fully_explained() -> None:
    diff = diff_from_added("app/s.py", ["h = md5(p)", "eval(x)", "def public_api():"])
    result = await run_review(make_pr(), diff, router=LLMRouter(FakeProvider()), use_llm=False)
    assert result.findings
    for f in result.findings:
        exp = f.explanation
        assert exp.why.strip()
        assert exp.impact.strip()
        assert exp.alternative.strip()
        assert exp.complexity.strip()
        assert exp.references  # at least one citation
        assert 0.0 <= f.confidence <= 1.0
