"""Confidence-gated auto-approve tests (PRD §8.10)."""

from __future__ import annotations

from app.github.client import CheckConclusion, FakeGitHubReviewClient, ReviewEvent
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.publish.publisher import publish_review
from app.review.graph import run_review

from tests.conftest import diff_from_added, make_pr


async def test_docs_only_clean_pr_is_auto_approved() -> None:
    diff = diff_from_added("README.md", ["# Title", "Updated documentation."])
    result = await run_review(make_pr(), diff, router=LLMRouter(FakeProvider()))
    assert result.auto_approved
    assert not result.consensus.blocking

    client = FakeGitHubReviewClient()
    await publish_review(client, result)
    assert client.reviews[0].event is ReviewEvent.APPROVE
    assert client.checks[0][2] is CheckConclusion.SUCCESS


async def test_lockfile_bump_clean_pr_is_auto_approved() -> None:
    diff = diff_from_added("poetry.lock", ["package = '1.2.4'"])
    result = await run_review(make_pr(), diff, router=LLMRouter(FakeProvider()))
    assert result.auto_approved


async def test_eligible_but_dirty_pr_is_not_auto_approved() -> None:
    # A lockfile is auto-approve *eligible*, but a planted secret makes the review dirty,
    # so the confidence gate must refuse to auto-approve.
    diff = diff_from_added("requirements.txt", ["mypkg==1.0  # ghp_" + "A" * 36])
    result = await run_review(make_pr(), diff, router=LLMRouter(FakeProvider()))
    assert not result.auto_approved
    assert result.consensus.blocking  # the secret is a critical finding


async def test_normal_backend_pr_is_never_auto_approved() -> None:
    diff = diff_from_added("app/s.py", ["def f():", "    return 1"])
    result = await run_review(make_pr(), diff, router=LLMRouter(FakeProvider()))
    assert not result.auto_approved
    assert result.routing is not None
    assert not result.routing.auto_approve_eligible
