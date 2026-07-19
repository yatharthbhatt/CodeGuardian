"""Auto-Patch Generator tests (PRD §8.6)."""

from __future__ import annotations

import pytest
from app.domain.findings import Dimension, Explanation, Finding, FindingSource, Severity
from app.github.client import FakeGitHubReviewClient
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.patch.generator import generate_patch, generate_patches
from app.publish.publisher import publish_review
from app.review.graph import run_review

from tests.conftest import diff_from_added, make_pr


def _finding(category: str, file_path: str = "app/s.py", line: int = 1) -> Finding:
    return Finding(
        agent="security",
        dimension=Dimension.SECURITY,
        category=category,
        severity=Severity.MEDIUM,
        confidence=0.9,
        title="Issue",
        message="msg",
        file_path=file_path,
        line=line,
        source=FindingSource.DETERMINISTIC,
        explanation=Explanation(why="w", impact="i"),
    )


@pytest.mark.parametrize(
    ("category", "line_text", "expected"),
    [
        ("weak-hash", "digest = md5(p)", "digest = sha256(p)"),
        (
            "tls-verification-disabled",
            "requests.get(u, verify=False)",
            "requests.get(u, verify=True)",
        ),
        ("insecure-deserialization", "data = yaml.load(s)", "data = yaml.safe_load(s)"),
        ("debug-enabled", "DEBUG = True", "DEBUG = False"),
    ],
)
def test_generate_patch_applies_mechanical_fix(
    category: str, line_text: str, expected: str
) -> None:
    diff = diff_from_added("app/s.py", [line_text])
    patch = generate_patch(_finding(category), diff)
    assert patch is not None
    assert patch.fixed == expected
    assert patch.original == line_text
    assert "```suggestion" in patch.suggestion_block()


def test_innerhtml_patch_in_js() -> None:
    diff = diff_from_added("web/a.js", ["el.innerHTML = user"])
    patch = generate_patch(_finding("xss-innerhtml", "web/a.js"), diff)
    assert patch is not None
    assert patch.fixed == "el.textContent = user"


def test_non_fixable_category_returns_none() -> None:
    diff = diff_from_added("app/s.py", ["eval(x)"])
    assert generate_patch(_finding("dangerous-eval"), diff) is None


def test_patch_skipped_when_line_not_in_diff() -> None:
    diff = diff_from_added("app/s.py", ["digest = md5(p)"])
    assert generate_patch(_finding("weak-hash", line=99), diff) is None


def test_generate_patches_stamps_finding() -> None:
    diff = diff_from_added("app/s.py", ["digest = md5(p)"])
    f = _finding("weak-hash")
    patches = generate_patches([f], diff)
    assert len(patches) == 1
    assert f.suggested_patch is not None
    assert "sha256" in f.suggested_patch


async def test_suggestion_block_posted_on_pr(router) -> None:  # type: ignore[no-untyped-def]
    # A real review of code using md5 should produce an inline comment with a suggestion.
    diff = diff_from_added("app/s.py", ["import hashlib", "h = md5(password)"])
    result = await run_review(make_pr(), diff, router=LLMRouter(FakeProvider()), use_llm=False)
    assert any(p.category == "weak-hash" for p in result.patches)

    client = FakeGitHubReviewClient()
    await publish_review(client, result)
    bodies = "\n".join(c.body for c in client.reviews[0].comments)
    assert "```suggestion" in bodies
    assert "sha256" in bodies
