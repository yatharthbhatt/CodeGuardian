"""Memory ↔ orchestrator integration (PRD §11).

Proves that repository memory changes the review: circular-dependency detection in the
Architecture agent, blast-radius findings surfaced, and regression risk that only appears
once history has accrued (memory improves the review over time).
"""

from __future__ import annotations

from app.memory.graph.inmemory import InMemoryGraphStore
from app.memory.service import RepositoryMemory
from app.review.graph import run_review

from tests.conftest import diff_from_added, diff_from_files, make_pr_n


def _mem() -> RepositoryMemory:
    return RepositoryMemory(InMemoryGraphStore())


async def test_circular_dependency_finding_surfaced() -> None:
    m = _mem()
    # a.py imports b, b.py imports a — a cycle introduced in one PR.
    diff = diff_from_files(
        [
            ("app/a.py", ["from app.b import y", "def a(): ..."]),
            ("app/b.py", ["from app.a import a", "def y(): ..."]),
        ]
    )
    result = await run_review(make_pr_n(1), diff, memory=m, use_llm=False)
    assert any(f.category == "circular-dependency" for f in result.findings)
    assert result.memory_context is not None
    assert result.memory_context.cycles


async def test_blast_radius_finding_on_later_pr() -> None:
    m = _mem()
    # PR1 establishes that a.py depends on b.py.
    await run_review(
        make_pr_n(1),
        diff_from_files([("app/a.py", ["from app.b import x"]), ("app/b.py", ["def x(): ..."])]),
        memory=m,
        use_llm=False,
    )
    # PR2 touches b.py → blast-radius finding lists a.py as impacted.
    result = await run_review(
        make_pr_n(2), diff_from_added("app/b.py", ["def x(): return 2"]), memory=m, use_llm=False
    )
    blast = [f for f in result.findings if f.category == "blast-radius"]
    assert blast
    assert "app/a.py" in blast[0].message


async def test_memory_adds_regression_risk_on_repeat_touch() -> None:
    m = _mem()
    # A fix PR touches auth.py, recording bug history.
    await run_review(
        make_pr_n(1, title="Fix auth bug"),
        diff_from_added("app/auth.py", ["def login(): ..."]),
        memory=m,
        use_llm=False,
    )
    # The next PR touching auth.py is flagged as regression-prone.
    result = await run_review(
        make_pr_n(2, title="Refactor auth"),
        diff_from_added("app/auth.py", ["def login(): return True"]),
        memory=m,
        use_llm=False,
    )
    assert any(f.category == "regression-risk" for f in result.findings)


async def test_review_without_memory_has_no_memory_findings() -> None:
    result = await run_review(
        make_pr_n(1), diff_from_added("app/a.py", ["def a(): ..."]), use_llm=False
    )
    assert result.memory_context is None
    assert not any(f.agent == "memory" for f in result.findings)
