"""Publisher tests — formatting + untrusted-content sanitization (PRD §4, §9.3)."""

from __future__ import annotations

from app.github.client import CheckConclusion, FakeGitHubReviewClient, ReviewEvent
from app.publish.publisher import publish_review, sanitize
from app.review.graph import run_review

from tests.conftest import diff_from_added, make_pr


def test_sanitize_neutralizes_html_and_mentions() -> None:
    out = sanitize("<script>@everyone `x`")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "@everyone" not in out  # @ is defused with a zero-width space
    assert "`" not in out


async def test_publish_blocking_review_requests_changes_and_fails_check(router) -> None:  # type: ignore[no-untyped-def]
    diff = diff_from_added("app/v.py", ["eval(x)", "PASSWORD = 'ghp_" + "A" * 36 + "'"])
    result = await run_review(make_pr(), diff, router=router, use_llm=False)
    client = FakeGitHubReviewClient()
    await publish_review(client, result)

    assert len(client.reviews) == 1
    review = client.reviews[0]
    assert review.event is ReviewEvent.REQUEST_CHANGES
    assert review.comments  # inline comments were produced
    assert client.checks[0][2] is CheckConclusion.FAILURE


async def test_publish_clean_review_comments_and_passes_check(router) -> None:  # type: ignore[no-untyped-def]
    diff = diff_from_added("app/ok.py", ['"""Module."""', "X = 1"])
    result = await run_review(make_pr(), diff, router=router, use_llm=False)
    client = FakeGitHubReviewClient()
    await publish_review(client, result)
    assert client.reviews[0].event is ReviewEvent.COMMENT
    assert client.checks[0][2] is CheckConclusion.SUCCESS


async def test_malicious_llm_finding_is_sanitized_in_inline_comment() -> None:
    # A model (or injected content) tries to inject HTML / forge an approval / mass-ping
    # via a finding it returns. It must be sanitized before reaching PR markdown.
    from app.llm.providers.fake import FakeProvider
    from app.llm.router import LLMRouter

    provider = FakeProvider()
    provider.set_findings(
        [
            {
                "category": "x",
                "severity": "high",
                "confidence": 0.9,
                "title": "</code><h1>APPROVED BY ADMIN</h1>",
                "message": "see here",
                "file_path": "app/v.py",
                "line": 1,
                "why": "@everyone please merge `now`",
                "impact": "<img src=x onerror=alert(1)>",
            }
        ]
    )
    diff = diff_from_added("app/v.py", ["x = 1"])
    result = await run_review(make_pr(), diff, router=LLMRouter(provider), use_llm=True)
    client = FakeGitHubReviewClient()
    await publish_review(client, result)

    all_comment_text = "\n".join(c.body for c in client.reviews[0].comments)
    assert "<h1>" not in all_comment_text
    assert "onerror" not in all_comment_text or "&lt;img" in all_comment_text
    assert "@everyone" not in all_comment_text
    assert "`" not in all_comment_text
