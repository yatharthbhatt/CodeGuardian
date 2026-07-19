"""Point CodeGuardian at the local ``demo-repo/`` and print the review (offline).

Reads the demo repo's source files, treats them as an all-new diff, runs the full review
pipeline with the offline FakeProvider (no network / no API key), and prints the findings,
auto-fix suggestions, and risk scorecard. Run: `python -m examples.review_demo_repo`
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.github.client import FakeGitHubReviewClient
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.review.diff import AddedLine, FileDiff, NormalizedDiff
from app.review.state import PRMeta
from app.worker.pipeline import process_pull_request

_DEMO_DIR = Path(__file__).resolve().parents[2] / "demo-repo"
_SOURCE_GLOBS = ("*.py", "Dockerfile", "*.tf", "*.yml", "*.yaml")


def _load_demo_diff() -> NormalizedDiff:
    files: list[FileDiff] = []
    for path in sorted(_DEMO_DIR.rglob("*")):
        if not path.is_file() or path.name == "README.md":
            continue
        if not (path.suffix in {".py", ".tf", ".yml", ".yaml"} or path.name == "Dockerfile"):
            continue
        rel = path.relative_to(_DEMO_DIR).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        files.append(
            FileDiff(
                path=rel,
                is_new_file=True,
                added=[AddedLine(new_line=i + 1, text=t) for i, t in enumerate(lines)],
            )
        )
    return NormalizedDiff(files=files)


async def main() -> None:
    pr = PRMeta(
        tenant_id="demo",
        repo_full_name="acme/demo",
        number=1,
        title="Add login + config loading",
        body="Implements user login and config loading.",
        author="dev",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )
    client = FakeGitHubReviewClient()
    result = await process_pull_request(
        pr, _load_demo_diff(), client=client, router=LLMRouter(FakeProvider()), use_llm=False
    )

    print("=" * 72)
    print(f"CodeGuardian AI review of demo-repo/  —  {len(result.findings)} findings")
    print(
        f"Overall Engineering Score: {result.risk['overall']}/100   "
        f"Verdict: {client.reviews[0].event.value}"
    )
    print("=" * 72)
    for f in sorted(result.findings, key=lambda x: -x.severity.weight):
        loc = f"{f.file_path}:{f.line}" if f.file_path else "(repo)"
        patch = " [auto-fix available]" if f.suggested_patch else ""
        print(f"  [{f.severity.value:8}] {f.category:26} {loc}{patch}")
    print("=" * 72)
    print(f"Auto-fix suggestions generated: {len(result.patches)}")


if __name__ == "__main__":
    asyncio.run(main())
