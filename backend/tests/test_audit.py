"""Hash-chained audit log (PRD §9.8) — append-only + tamper-evident + tenant-scoped."""

from __future__ import annotations

from app.dashboard.audit import HashChainedAuditLog


def test_chain_links_and_verifies() -> None:
    log = HashChainedAuditLog()
    e1 = log.record("t", "alice", "review.published", {"pr": 1})
    e2 = log.record("t", "bob", "feedback.record", {"category": "x"})
    assert e1.prev_hash == "0" * 64  # genesis
    assert e2.prev_hash == e1.hash  # chained
    assert log.verify("t") is True


def test_tamper_is_detected() -> None:
    log = HashChainedAuditLog()
    log.record("t", "alice", "a", {"v": 1})
    log.record("t", "bob", "b", {"v": 2})
    # Mutate a stored event's detail out from under the chain.
    log._chains["t"][0].detail["v"] = 999
    assert log.verify("t") is False


def test_reorder_is_detected() -> None:
    log = HashChainedAuditLog()
    log.record("t", "a", "one", {})
    log.record("t", "a", "two", {})
    chain = log._chains["t"]
    chain[0], chain[1] = chain[1], chain[0]
    assert log.verify("t") is False


def test_tenant_isolation() -> None:
    log = HashChainedAuditLog()
    log.record("A", "alice", "secret.action", {"x": 1})
    assert log.list_events("B") == []
    assert log.verify("B") is True  # empty chain is trivially valid


def test_list_events_is_newest_first_and_redaction_friendly() -> None:
    log = HashChainedAuditLog()
    log.record("t", "a", "first", {})
    log.record("t", "a", "second", {})
    events = log.list_events("t")
    assert events[0]["action"] == "second"
    assert {"seq", "actor", "action", "ts", "hash", "prev_hash"} <= set(events[0])
