"""Detection-quality metrics for the eval harness."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseResult:
    id: str
    expected: frozenset[str]
    predicted: frozenset[str]


@dataclass(frozen=True)
class EvalReport:
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    true_positives: int
    false_positives: int
    false_negatives: int
    cases: tuple[CaseResult, ...]

    def as_dict(self) -> dict[str, float | int]:
        return {
            "precision": round(self.precision, 3),
            "recall": round(self.recall, 3),
            "f1": round(self.f1, 3),
            "false_positive_rate": round(self.false_positive_rate, 3),
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
        }


def aggregate(cases: list[CaseResult]) -> EvalReport:
    tp = fp = fn = 0
    clean = fp_cases = 0
    for c in cases:
        tp += len(c.expected & c.predicted)
        fp += len(c.predicted - c.expected)
        fn += len(c.expected - c.predicted)
        if not c.expected:  # a clean probe
            clean += 1
            if c.predicted:
                fp_cases += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp_cases / clean if clean else 0.0
    return EvalReport(
        precision=precision,
        recall=recall,
        f1=f1,
        false_positive_rate=fpr,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        cases=tuple(cases),
    )
