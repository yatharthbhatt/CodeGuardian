"""Offline demo of repository memory across a sequence of PRs.

Shows the knowledge graph learning over time: a bug fix records history, an import
establishes a dependency, and a later PR then gets **blast-radius** + **regression-risk**
findings that a stateless reviewer could never produce. Run: `python -m examples.demo_memory`
"""

from __future__ import annotations

import asyncio

from app.github.client import FakeGitHubReviewClient
from app.memory.graph.inmemory import InMemoryGraphStore
from app.memory.service import RepositoryMemory
from app.review.diff import NormalizedDiff, parse_unified_diff
from app.review.graph import ReviewResult
from app.review.state import PRMeta
from app.worker.pipeline import process_pull_request


def _pr(number: int, title: str) -> PRMeta:
    return PRMeta(
        tenant_id="demo",
        repo_full_name="acme/shop",
        number=number,
        title=title,
        body="",
        author="dev",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )


def _diff(*files: tuple[str, list[str]]) -> NormalizedDiff:
    """Build a raw unified diff from (path, added-lines) pairs, then parse it."""
    chunks: list[str] = []
    for path, lines in files:
        body = "\n".join(f"+{ln}" for ln in lines)
        chunks.append(
            f"diff --git a/{path} b/{path}\n"
            f"new file mode 100644\n--- /dev/null\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}"
        )
    return parse_unified_diff("\n".join(chunks) + "\n")


async def main() -> None:
    memory = RepositoryMemory(InMemoryGraphStore())

    async def review(pr: PRMeta, diff: NormalizedDiff) -> ReviewResult:
        return await process_pull_request(
            pr, diff, client=FakeGitHubReviewClient(), memory=memory, use_llm=False
        )

    # PR #1: payment service imports the db module (payment.py DEPENDS_ON app/db.py).
    await review(_pr(1, "Add payment service"), _diff(("app/payment.py", ["from app.db import q"])))
    # PR #2: a bug fix in the db layer (records bug history for app/db.py).
    await review(_pr(2, "Fix crash in db layer"), _diff(("app/db.py", ["def q(): return 1"])))

    # PR #3 touches ONLY db.py: it has bug history (regression risk) AND payment.py
    # depends on it (blast radius) — both insights a stateless reviewer would miss.
    result = await review(_pr(3, "Refactor db layer"), _diff(("app/db.py", ["def q(): return 2"])))

    print("=" * 70)
    print("PR #3 review — repository memory in action")
    print("=" * 70)
    ctx = result.memory_context
    if ctx is not None:
        print(f"Blast radius (impacted files): {ctx.blast_radius}")
        print(
            f"Regression-prone files: {[(r.file_path, r.past_bug_count) for r in ctx.regression]}"
        )
    print("-" * 70)
    for f in result.findings:
        if f.agent == "memory":
            print(f"[{f.severity.value:8}] {f.category}: {f.title}")
            print(f"           {f.message}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
