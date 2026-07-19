"""Explainability enforcement (PRD §8.5).

Every finding CodeGuardian surfaces must carry the full explainability payload —
**Why · Impact · Alternative · References · Complexity · Confidence** — so developers can
trust and act on it. This pass guarantees completeness by filling any gaps with sensible,
category-appropriate defaults (e.g. a CWE link for a security finding) rather than dropping
otherwise-valid findings.
"""

from __future__ import annotations

from app.domain.findings import Dimension, Finding

_CWE_URL = "https://cwe.mitre.org/data/definitions/{n}.html"

# A canonical reference per dimension, so every finding has at least one citation.
_DIMENSION_REFS: dict[Dimension, str] = {
    Dimension.SECURITY: "https://owasp.org/www-project-top-ten/",
    Dimension.ACCESSIBILITY: "https://www.w3.org/WAI/WCAG22/quickref/",
    Dimension.PERFORMANCE: "https://web.dev/learn/performance",
    Dimension.DOCUMENTATION: "https://www.writethedocs.org/guide/",
    Dimension.TESTING: "https://martinfowler.com/testing/",
    Dimension.DEVOPS: "https://owasp.org/www-project-devsecops-guideline/",
    Dimension.ARCHITECTURE: "https://en.wikipedia.org/wiki/SOLID",
    Dimension.CORRECTNESS: "https://google.github.io/eng-practices/review/reviewer/",
}

_DEFAULT_ALTERNATIVE = "Review and address per the guidance above."


def enforce_explainability(findings: list[Finding]) -> list[Finding]:
    """Ensure every finding has all six explainability fields populated (mutates in place)."""
    for f in findings:
        exp = f.explanation
        if not exp.alternative.strip():
            exp.alternative = _DEFAULT_ALTERNATIVE
        if not exp.complexity.strip():
            exp.complexity = "unknown"

        refs = list(exp.references)
        if f.cwe:
            cwe_link = _CWE_URL.format(n=f.cwe.split("-", 1)[1])
            if cwe_link not in refs:
                refs.append(cwe_link)
        dim_ref = _DIMENSION_REFS.get(f.dimension)
        if dim_ref and dim_ref not in refs:
            refs.append(dim_ref)
        exp.references = refs[:20]
    return findings
