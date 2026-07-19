"""Feedback store + Golden-Path learner + consensus integration (PRD §8.12)."""

from __future__ import annotations

from app.domain.findings import Dimension, Explanation, Finding, FindingSource, Severity
from app.feedback.learner import GoldenPathLearner
from app.feedback.store import FeedbackAction, InMemoryFeedbackStore
from app.review.consensus import Gate, build_consensus
from fastapi.testclient import TestClient


def _finding(category: str) -> Finding:
    return Finding(
        agent="architecture",
        dimension=Dimension.ARCHITECTURE,
        category=category,
        severity=Severity.LOW,
        confidence=0.8,
        title="Nit finding",
        message="msg",
        file_path="a.py",
        line=1,
        source=FindingSource.DETERMINISTIC,
        explanation=Explanation(why="w", impact="i"),
    )


def test_store_tracks_acceptance_rate_and_is_tenant_scoped() -> None:
    store = InMemoryFeedbackStore()
    for _ in range(3):
        store.record("A", "octo/repo", "wildcard-import", FeedbackAction.REJECTED)
    store.record("A", "octo/repo", "wildcard-import", FeedbackAction.ACCEPTED)
    stats = store.stats("A", "octo/repo")["wildcard-import"]
    assert stats.total == 4
    assert stats.acceptance_rate == 0.25
    # Tenant B sees nothing.
    assert store.stats("B", "octo/repo") == {}


def test_learner_needs_minimum_samples() -> None:
    store = InMemoryFeedbackStore()
    store.record("A", "r/r", "cat", FeedbackAction.REJECTED)
    learner = GoldenPathLearner(store)
    assert learner.adjustments("A", "r/r") == {}  # below min samples → no adaptation


def test_learner_downweights_frequently_rejected_category() -> None:
    store = InMemoryFeedbackStore()
    for _ in range(10):
        store.record("A", "r/r", "broad-except", FeedbackAction.REJECTED)
    adj = GoldenPathLearner(store).adjustments("A", "r/r")
    assert adj["broad-except"] < 0.5  # heavily rejected → strong down-weight


def test_learner_keeps_accepted_category_at_full_weight() -> None:
    store = InMemoryFeedbackStore()
    for _ in range(10):
        store.record("A", "r/r", "sql-injection", FeedbackAction.ACCEPTED)
    adj = GoldenPathLearner(store).adjustments("A", "r/r")
    assert adj["sql-injection"] == 1.0


def test_consensus_applies_adjustments_to_suppress_noise() -> None:
    findings = [_finding("wildcard-import")]
    # Without feedback the finding at least collapses (visible).
    base = build_consensus(findings)
    assert base.items[0].gate is not Gate.SUPPRESS
    # With a strong down-weight, the same finding is suppressed (noise control).
    adjusted = build_consensus(findings, {"wildcard-import": 0.4})
    assert adjusted.items[0].weighted_confidence < base.items[0].weighted_confidence
    assert adjusted.items[0].gate is Gate.SUPPRESS


def _seed_member(client: TestClient) -> None:
    from app.api.auth import Principal
    from app.core.security.rbac import Role

    v = client.app.state.token_verifier  # type: ignore[attr-defined]
    v.add("member", Principal("t-1", "dev", Role.MEMBER))
    v.add("reader", Principal("t-1", "obs", Role.READ_ONLY))


def _body() -> dict[str, str]:
    return {"repo": "octo/repo", "category": "broad-except", "action": "rejected"}


def test_feedback_requires_auth(client: TestClient) -> None:
    assert client.post("/api/v1/feedback", json=_body()).status_code == 401


def test_feedback_requires_member_role(client: TestClient) -> None:
    _seed_member(client)
    resp = client.post("/api/v1/feedback", json=_body(), headers={"Authorization": "Bearer reader"})
    assert resp.status_code == 403


def test_feedback_endpoint_records_and_audits(client: TestClient) -> None:
    _seed_member(client)
    resp = client.post("/api/v1/feedback", json=_body(), headers={"Authorization": "Bearer member"})
    assert resp.status_code == 200
    # Tenant comes from the token ("t-1"), never the body.
    stats = client.app.state.feedback_store.stats("t-1", "octo/repo")  # type: ignore[attr-defined]
    assert stats["broad-except"].rejected == 1
    # The action was written to the immutable audit log.
    audit = client.app.state.audit_store  # type: ignore[attr-defined]
    events = audit.list_events("t-1")
    assert events and events[0]["action"] == "feedback.record"
    assert audit.verify("t-1") is True


def test_feedback_endpoint_rejects_invalid_action(client: TestClient) -> None:
    _seed_member(client)
    resp = client.post(
        "/api/v1/feedback",
        json={"repo": "o/r", "category": "c", "action": "bogus"},
        headers={"Authorization": "Bearer member"},
    )
    assert resp.status_code == 422
