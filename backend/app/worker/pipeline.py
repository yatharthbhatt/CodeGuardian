"""End-to-end review pipeline (the testable core of the async worker).

Given a PR + diff and the wired dependencies, run the LangGraph review and publish the
result. Kept free of I/O wiring so it can be integration-tested offline with a
``FakeProvider`` + ``FakeGitHubReviewClient``.
"""

from __future__ import annotations

import time

from app.dashboard.store import AnalyticsStore, summarize
from app.github.client import GitHubReviewClient
from app.llm.router import LLMRouter
from app.memory.service import RepositoryMemory
from app.publish.publisher import publish_review
from app.review.diff import NormalizedDiff
from app.review.graph import ReviewResult, run_review
from app.review.state import PRMeta


async def process_pull_request(
    pr: PRMeta,
    diff: NormalizedDiff,
    *,
    client: GitHubReviewClient,
    router: LLMRouter | None = None,
    token_budget: int = 120_000,
    use_llm: bool = True,
    checkpointer: object = None,
    memory: RepositoryMemory | None = None,
    analytics: AnalyticsStore | None = None,
) -> ReviewResult:
    start = time.perf_counter()
    result = await run_review(
        pr,
        diff,
        router=router,
        token_budget=token_budget,
        use_llm=use_llm,
        checkpointer=checkpointer,
        thread_id=f"{pr.repo_full_name}#{pr.number}@{pr.head_sha}",
        memory=memory,
    )
    await publish_review(client, result)
    # Feed the dashboard read-model (tenant-scoped by the summary's tenant).
    if analytics is not None:
        latency_ms = round((time.perf_counter() - start) * 1000)
        analytics.record(pr.tenant_id, summarize(result, latency_ms=latency_ms))
    return result
