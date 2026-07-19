"""Shared pytest fixtures."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from app.config import Settings
from app.core.security.webhook import compute_signature
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import SecretStr

WEBHOOK_SECRET = "test-webhook-secret-value"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        github_webhook_secret=SecretStr(WEBHOOK_SECRET),
        webhook_replay_window_seconds=300,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return compute_signature(secret, body)


@pytest.fixture
def pr_event_payload() -> dict[str, Any]:
    """A minimal, valid `pull_request` webhook body."""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "number": 42,
            "title": "Add feature",
            "body": "Implements the thing.",
            "state": "open",
            "draft": False,
            "head": {"sha": "a" * 40, "ref": "feature/x"},
            "base": {"sha": "b" * 40, "ref": "main"},
            "user": {"login": "octocat", "id": 1},
        },
        "repository": {"id": 100, "full_name": "octo/repo", "private": False},
        "sender": {"login": "octocat", "id": 1},
        "installation": {"id": 555},
    }


@pytest.fixture
def pr_event_bytes(pr_event_payload: dict[str, Any]) -> bytes:
    return json.dumps(pr_event_payload).encode()


# --- Phase 1 fixtures ------------------------------------------------------
@pytest.fixture
def fake_provider():  # type: ignore[no-untyped-def]
    from app.llm.providers.fake import FakeProvider

    return FakeProvider()


@pytest.fixture
def router(fake_provider):  # type: ignore[no-untyped-def]
    from app.llm.router import LLMRouter

    return LLMRouter(fake_provider)


def make_pr(title: str = "Add feature", body: str = "Implements the thing.") -> Any:
    from app.review.state import PRMeta

    return PRMeta(
        tenant_id="t-1",
        repo_full_name="octo/repo",
        number=42,
        title=title,
        body=body,
        author="octocat",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )


def diff_from_added(path: str, lines: list[str], *, new_file: bool = True) -> Any:
    """Build a NormalizedDiff directly from added lines (skips diff-text plumbing)."""
    return diff_from_files([(path, lines)], new_file=new_file)


def diff_from_files(files: list[tuple[str, list[str]]], *, new_file: bool = True) -> Any:
    """Build a multi-file NormalizedDiff from (path, added-lines) pairs."""
    from app.review.diff import AddedLine, FileDiff, NormalizedDiff

    fds = [
        FileDiff(
            path=p,
            is_new_file=new_file,
            added=[AddedLine(new_line=i + 1, text=t) for i, t in enumerate(ls)],
        )
        for p, ls in files
    ]
    return NormalizedDiff(files=fds)


def make_pr_n(
    number: int,
    *,
    title: str = "Add feature",
    body: str = "",
    repo: str = "octo/repo",
    tenant: str = "t-1",
) -> Any:
    """A PRMeta with an explicit number/title (for memory tests spanning PRs)."""
    from app.review.state import PRMeta

    return PRMeta(
        tenant_id=tenant,
        repo_full_name=repo,
        number=number,
        title=title,
        body=body,
        author="dev",
        head_sha="a" * 40,
        base_sha="b" * 40,
    )
