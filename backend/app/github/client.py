"""GitHub review client — protocol + a fake (tests) + a real HTTP impl.

Everything that talks to GitHub goes through :class:`GitHubReviewClient` so the review
pipeline is fully testable offline via :class:`FakeGitHubReviewClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class ReviewEvent(StrEnum):
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class CheckConclusion(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"


@dataclass
class ReviewComment:
    path: str
    line: int
    body: str


@dataclass
class ReviewRequest:
    repo_full_name: str
    pr_number: int
    head_sha: str
    event: ReviewEvent
    body: str
    comments: list[ReviewComment] = field(default_factory=list)


class GitHubReviewClient(Protocol):
    async def create_review(self, req: ReviewRequest) -> None: ...

    async def create_check_run(
        self, repo_full_name: str, head_sha: str, conclusion: CheckConclusion, summary: str
    ) -> None: ...


@dataclass
class FakeGitHubReviewClient:
    """Records calls instead of hitting GitHub."""

    reviews: list[ReviewRequest] = field(default_factory=list)
    checks: list[tuple[str, str, CheckConclusion, str]] = field(default_factory=list)

    async def create_review(self, req: ReviewRequest) -> None:
        self.reviews.append(req)

    async def create_check_run(
        self, repo_full_name: str, head_sha: str, conclusion: CheckConclusion, summary: str
    ) -> None:
        self.checks.append((repo_full_name, head_sha, conclusion, summary))


class HttpGitHubReviewClient:
    """Real client using a short-lived installation token (PRD §9.1).

    Network-backed; exercised in integration/e2e environments, not the offline unit suite.
    """

    _API = "https://api.github.com"

    def __init__(self, installation_token: str) -> None:
        self._token = installation_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def create_review(self, req: ReviewRequest) -> None:
        import httpx

        url = f"{self._API}/repos/{req.repo_full_name}/pulls/{req.pr_number}/reviews"
        payload = {
            "commit_id": req.head_sha,
            "event": req.event.value,
            "body": req.body,
            "comments": [{"path": c.path, "line": c.line, "body": c.body} for c in req.comments],
        }
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()

    async def create_check_run(
        self, repo_full_name: str, head_sha: str, conclusion: CheckConclusion, summary: str
    ) -> None:
        import httpx

        url = f"{self._API}/repos/{repo_full_name}/check-runs"
        payload = {
            "name": "CodeGuardian AI",
            "head_sha": head_sha,
            "status": "completed",
            "conclusion": conclusion.value,
            "output": {"title": "CodeGuardian AI review", "summary": summary},
        }
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
