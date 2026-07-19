"""Eval harness tests (PRD §19) — metrics math + a quality gate on current agents."""

from __future__ import annotations

from evals.metrics import CaseResult, aggregate
from evals.runner import run_evals


def test_metrics_math() -> None:
    cases = [
        CaseResult("a", frozenset({"x"}), frozenset({"x"})),  # TP
        CaseResult("b", frozenset({"y"}), frozenset()),  # FN
        CaseResult("c", frozenset(), frozenset({"z"})),  # FP (clean probe flagged)
        CaseResult("d", frozenset(), frozenset()),  # clean, correct
    ]
    r = aggregate(cases)
    assert r.true_positives == 1
    assert r.false_positives == 1
    assert r.false_negatives == 1
    assert r.precision == 0.5
    assert r.recall == 0.5
    assert r.false_positive_rate == 0.5  # 1 of 2 clean probes flagged


async def test_harness_runs_and_meets_quality_gate() -> None:
    report = await run_evals()
    # The deterministic Security agent should catch all labeled vulns…
    assert report.recall >= 0.8
    # …without flagging the clean / false-positive probes.
    assert report.false_positive_rate == 0.0
    assert report.precision >= 0.9


async def test_every_positive_case_is_detected() -> None:
    report = await run_evals()
    misses = [c.id for c in report.cases if c.expected and not (c.expected <= c.predicted)]
    assert misses == []
