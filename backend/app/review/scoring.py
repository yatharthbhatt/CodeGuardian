"""Risk Scorecard (PRD §7).

Each dimension starts at 100 and loses points proportional to finding severity x weighted
confidence. Maintainability and technical debt are derived from architecture + docs + test
+ devops signal. Correctness (bugs) and accessibility findings also pull down the overall
Engineering Score, which is a weighted blend (higher = healthier).

The returned keys match the persisted ``risk_scorecards`` columns (PRD §10); the extra
dimensions (correctness/testing/devops/accessibility) fold into overall + the derived rows.
"""

from __future__ import annotations

from app.domain.findings import Dimension, Finding

_START = 100.0
_FLOOR = 0.0


def _penalty(findings: list[Finding], dimension: Dimension) -> float:
    return sum(
        f.severity.weight * max(f.confidence, 0.1) for f in findings if f.dimension is dimension
    )


def build_scorecard(findings: list[Finding]) -> dict[str, float]:
    pen = {dim: _penalty(findings, dim) for dim in Dimension}

    security = _clamp(_START - pen[Dimension.SECURITY])
    architecture = _clamp(_START - pen[Dimension.ARCHITECTURE])
    performance = _clamp(_START - pen[Dimension.PERFORMANCE])
    documentation = _clamp(_START - pen[Dimension.DOCUMENTATION])
    correctness = _clamp(_START - pen[Dimension.CORRECTNESS])
    accessibility = _clamp(_START - pen[Dimension.ACCESSIBILITY])

    # Derived rows blend architecture/docs/testing/devops signal.
    debt_signal = (
        pen[Dimension.ARCHITECTURE]
        + pen[Dimension.DOCUMENTATION]
        + pen[Dimension.TESTING]
        + pen[Dimension.DEVOPS]
    )
    maintainability = _clamp(_START - 0.6 * debt_signal)
    tech_debt = _clamp(
        _START
        - 0.8 * (pen[Dimension.ARCHITECTURE] + pen[Dimension.TESTING] + pen[Dimension.DEVOPS])
    )

    # Overall blend — correctness (bugs) and security weigh most.
    overall = (
        0.28 * security
        + 0.18 * correctness
        + 0.12 * architecture
        + 0.12 * performance
        + 0.12 * maintainability
        + 0.10 * tech_debt
        + 0.05 * documentation
        + 0.03 * accessibility
    )

    return {
        "security": round(security, 1),
        "architecture": round(architecture, 1),
        "performance": round(performance, 1),
        "maintainability": round(maintainability, 1),
        "documentation": round(documentation, 1),
        "tech_debt": round(tech_debt, 1),
        "overall": round(overall, 1),
    }


def _clamp(value: float) -> float:
    return max(_FLOOR, min(_START, value))
