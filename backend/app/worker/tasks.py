"""Celery task: review a pull request end-to-end (PRD §4).

Flow (production): authenticate as the GitHub App → mint a short-lived installation token
→ fetch the PR diff → run the review pipeline → publish. Idempotent on the review key so
at-least-once delivery and retries never double-post.

Network wiring lives here; the pure pipeline (``worker/pipeline.py``) is what the offline
integration tests exercise.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings
from app.github.auth import GitHubAppAuth, InstallationTokenClient
from app.github.client import HttpGitHubReviewClient
from app.llm.providers.claude import ClaudeProvider
from app.llm.router import LLMRouter
from app.review.diff import parse_unified_diff
from app.review.state import PRMeta
from app.schemas.github import PullRequestEvent
from app.worker.celery_app import celery_app
from app.worker.pipeline import process_pull_request

log = logging.getLogger("codeguardian.worker")

# Process-local idempotency cache; the durable check is the reviews table (unique
# idempotency_key) — see app/db/models.py::Review.
_processed: set[str] = set()


def _idempotency_key(event: PullRequestEvent) -> str:
    return f"{event.repository.id}:{event.number}:{event.pull_request.head.sha}"


@celery_app.task(name="reviews.review_pull_request", bind=True, max_retries=3)  # type: ignore[untyped-decorator]
def review_pull_request(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Celery entrypoint. Validates, guards idempotency, runs the async pipeline."""
    event = PullRequestEvent.model_validate(payload)
    key = _idempotency_key(event)
    if key in _processed:
        log.info("review skipped (already processed)", extra={"idempotency_key": key})
        return {"status": "duplicate", "idempotency_key": key}
    try:
        result = asyncio.run(_run(event))
    except Exception as exc:
        log.exception("review task failed", extra={"idempotency_key": key})
        raise self.retry(exc=exc, countdown=30) from exc
    _processed.add(key)
    return result


async def _run(event: PullRequestEvent) -> dict[str, Any]:
    settings = get_settings()
    if not (settings.github_app_id and settings.github_app_private_key):
        raise RuntimeError("GitHub App credentials are not configured.")
    if event.installation is None:
        raise RuntimeError("Webhook has no installation id; cannot mint a token.")

    auth = GitHubAppAuth(settings.github_app_id, settings.github_app_private_key.get_secret_value())
    token = await auth.installation_token(event.installation.id, _http_token_client())

    diff_text = await _fetch_pr_diff(event.repository.full_name, event.number, token)
    diff = parse_unified_diff(diff_text)

    pr = PRMeta(
        tenant_id=str(event.repository.id),  # mapped to real tenant in Phase 6 RBAC
        repo_full_name=event.repository.full_name,
        number=event.number,
        title=event.pull_request.title,
        body=event.pull_request.body or "",
        author=event.pull_request.user.login,
        head_sha=event.pull_request.head.sha,
        base_sha=event.pull_request.base.sha,
    )

    router = None
    if settings.anthropic_api_key:
        router = LLMRouter(ClaudeProvider(settings.anthropic_api_key.get_secret_value()))

    client = HttpGitHubReviewClient(token)
    result = await process_pull_request(
        pr, diff, client=client, router=router, token_budget=settings.per_pr_token_budget
    )
    return {
        "status": "reviewed",
        "overall": result.risk.get("overall", 0),
        "posted": len(result.consensus.posted),
        "tokens": result.tokens_used,
    }


def _http_token_client() -> InstallationTokenClient:
    class _Client(InstallationTokenClient):
        async def fetch_installation_token(self, app_jwt: str, installation_id: int) -> str:
            import httpx

            url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
            headers = {
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            async with httpx.AsyncClient(timeout=30) as http:
                resp = await http.post(url, headers=headers)
                resp.raise_for_status()
                return str(resp.json()["token"])

    return _Client()


async def _fetch_pr_diff(repo_full_name: str, number: int, token: str) -> str:
    import httpx

    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{number}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text
