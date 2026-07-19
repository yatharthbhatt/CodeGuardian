"""Webhook authentication + replay + validation tests (PRD §9.9)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from app.core.security.webhook import (
    InMemoryReplayGuard,
    ReplayError,
    SignatureError,
    compute_signature,
    verify_signature,
)
from fastapi.testclient import TestClient

from tests.conftest import WEBHOOK_SECRET, sign


# --- unit: signature ------------------------------------------------------
def test_verify_signature_accepts_valid() -> None:
    body = b'{"hello":"world"}'
    verify_signature(WEBHOOK_SECRET, body, compute_signature(WEBHOOK_SECRET, body))


def test_verify_signature_rejects_tampered_body() -> None:
    good = compute_signature(WEBHOOK_SECRET, b"original")
    with pytest.raises(SignatureError):
        verify_signature(WEBHOOK_SECRET, b"tampered", good)


def test_verify_signature_rejects_wrong_secret() -> None:
    body = b"payload"
    with pytest.raises(SignatureError):
        verify_signature(WEBHOOK_SECRET, body, compute_signature("other-secret", body))


@pytest.mark.parametrize("header", [None, "", "sha1=deadbeef", "not-a-sig", "sha256="])
def test_verify_signature_rejects_malformed_header(header: str | None) -> None:
    with pytest.raises(SignatureError):
        verify_signature(WEBHOOK_SECRET, b"x", header)


def test_verify_signature_fails_closed_without_secret() -> None:
    body = b"x"
    with pytest.raises(SignatureError):
        verify_signature("", body, compute_signature("", body))


# --- unit: replay guard ---------------------------------------------------
def test_replay_guard_rejects_duplicates() -> None:
    guard = InMemoryReplayGuard(window_seconds=300)
    guard.check_and_remember("delivery-1")
    with pytest.raises(ReplayError):
        guard.check_and_remember("delivery-1")


def test_replay_guard_rejects_empty_id() -> None:
    with pytest.raises(ReplayError):
        InMemoryReplayGuard().check_and_remember("")


# --- integration: endpoint ------------------------------------------------
def _post(
    client: TestClient,
    body: bytes,
    *,
    sig: str | None,
    delivery: str,
    event: str = "pull_request",
) -> Any:
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }
    if sig is not None:
        headers["X-Hub-Signature-256"] = sig
    return client.post("/webhooks/github", content=body, headers=headers)


def test_endpoint_accepts_valid_signed_pr(client: TestClient, pr_event_bytes: bytes) -> None:
    resp = _post(client, pr_event_bytes, sig=sign(pr_event_bytes), delivery="d-ok")
    assert resp.status_code == 202
    assert resp.json()["status"] == "accepted"


def test_endpoint_rejects_missing_signature(client: TestClient, pr_event_bytes: bytes) -> None:
    resp = _post(client, pr_event_bytes, sig=None, delivery="d-nosig")
    assert resp.status_code == 401


def test_endpoint_rejects_bad_signature(client: TestClient, pr_event_bytes: bytes) -> None:
    resp = _post(client, pr_event_bytes, sig="sha256=" + "0" * 64, delivery="d-bad")
    assert resp.status_code == 401


def test_endpoint_rejects_tampered_body(client: TestClient, pr_event_bytes: bytes) -> None:
    sig = sign(pr_event_bytes)
    tampered = pr_event_bytes.replace(b"octo/repo", b"evil/repo")
    resp = _post(client, tampered, sig=sig, delivery="d-tamper")
    assert resp.status_code == 401


def test_endpoint_deduplicates_replayed_delivery(client: TestClient, pr_event_bytes: bytes) -> None:
    sig = sign(pr_event_bytes)
    first = _post(client, pr_event_bytes, sig=sig, delivery="d-replay")
    assert first.status_code == 202
    second = _post(client, pr_event_bytes, sig=sig, delivery="d-replay")
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate_ignored"


def test_endpoint_rejects_oversized_body(client: TestClient) -> None:
    big = b"x" * (5 * 1024 * 1024 + 1)
    resp = _post(client, big, sig=sign(big), delivery="d-big")
    assert resp.status_code == 413


def test_endpoint_rejects_invalid_json_after_valid_signature(client: TestClient) -> None:
    body = b"not json at all"
    resp = _post(client, body, sig=sign(body), delivery="d-badjson")
    assert resp.status_code == 400


def test_endpoint_rejects_malformed_payload(client: TestClient) -> None:
    # Valid JSON + valid signature but missing required fields → 422.
    body = json.dumps({"action": "opened"}).encode()
    resp = _post(client, body, sig=sign(body), delivery="d-malformed")
    assert resp.status_code == 422


def test_endpoint_skips_draft_pr(client: TestClient, pr_event_payload: dict[str, Any]) -> None:
    pr_event_payload["pull_request"]["draft"] = True
    body = json.dumps(pr_event_payload).encode()
    resp = _post(client, body, sig=sign(body), delivery="d-draft")
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_review"


def test_ping_event_returns_pong(client: TestClient) -> None:
    body = json.dumps({"zen": "hi", "hook_id": 1}).encode()
    resp = _post(client, body, sig=sign(body), delivery="d-ping", event="ping")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pong"
