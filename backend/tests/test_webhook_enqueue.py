"""The webhook enqueues a review after passing all security checks (PRD §4)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import sign


def test_valid_pr_is_enqueued(client: TestClient, pr_event_bytes: bytes) -> None:
    captured: list[dict[str, Any]] = []
    # Replace the app's enqueuer with a recorder (no broker needed).
    client.app.state.enqueuer = captured.append  # type: ignore[attr-defined]

    resp = client.post(
        "/webhooks/github",
        content=pr_event_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "enq-1",
            "X-Hub-Signature-256": sign(pr_event_bytes),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert len(captured) == 1
    assert captured[0]["repository"]["full_name"] == "octo/repo"


def test_unauthenticated_request_is_not_enqueued(client: TestClient, pr_event_bytes: bytes) -> None:
    captured: list[dict[str, Any]] = []
    client.app.state.enqueuer = captured.append  # type: ignore[attr-defined]

    resp = client.post(
        "/webhooks/github",
        content=pr_event_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "enq-2",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 401
    assert captured == []  # nothing enqueued on auth failure
