"""Run the review pipeline over the labeled dataset and score detection quality."""

from __future__ import annotations

from app.domain.findings import Dimension
from app.review.diff import AddedLine, FileDiff, NormalizedDiff
from app.review.state import PRMeta

from evals.dataset import DATASET, LabeledPR
from evals.metrics import CaseResult, EvalReport, aggregate


def _build_diff(files: tuple[tuple[str, tuple[str, ...]], ...]) -> NormalizedDiff:
    fds = [
        FileDiff(
            path=path,
            is_new_file=True,
            added=[AddedLine(new_line=i + 1, text=t) for i, t in enumerate(lines)],
        )
        for path, lines in files
    ]
    return NormalizedDiff(files=fds)


def _pr(case: LabeledPR) -> PRMeta:
    return PRMeta(
        tenant_id="eval",
        repo_full_name="eval/repo",
        number=1,
        title=case.title,
        body="",
        author="eval",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )


async def run_evals(dataset: tuple[LabeledPR, ...] = DATASET) -> EvalReport:
    # Import here to avoid importing the heavy orchestrator at module load.
    from app.review.graph import run_review

    cases: list[CaseResult] = []
    for case in dataset:
        result = await run_review(_pr(case), _build_diff(case.files), use_llm=False)
        predicted = frozenset(
            f.category for f in result.findings if f.dimension is Dimension.SECURITY
        )
        cases.append(CaseResult(id=case.id, expected=case.expected_security, predicted=predicted))
    return aggregate(cases)
