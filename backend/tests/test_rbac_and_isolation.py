"""RBAC ranking + verified multi-tenant isolation everywhere (PRD §9.2)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.core.security.rbac import Role, at_least, rank
from app.dashboard.audit import HashChainedAuditLog
from app.dashboard.store import InMemoryAnalyticsStore, ReviewSummary
from app.db import models  # noqa: F401  (register tables on Base.metadata)
from app.db.base import Base
from app.feedback.store import FeedbackAction, InMemoryFeedbackStore
from app.memory.graph.inmemory import InMemoryGraphStore
from app.memory.vector.base import Collection, VectorRecord
from app.memory.vector.embedding import HashingEmbedder
from app.memory.vector.inmemory import InMemoryVectorStore


# --- RBAC ------------------------------------------------------------------
def test_role_rank_ordering() -> None:
    assert rank(Role.READ_ONLY) < rank(Role.MEMBER) < rank(Role.MAINTAINER)
    assert rank(Role.MAINTAINER) < rank(Role.ADMIN) <= rank(Role.OWNER)
    assert rank(Role.SERVICE) >= rank(Role.ADMIN)  # internal high-trust principal


def test_at_least_matrix() -> None:
    assert at_least(Role.OWNER, Role.ADMIN)
    assert at_least(Role.MEMBER, Role.MEMBER)
    assert at_least(Role.SERVICE, Role.MAINTAINER)
    assert not at_least(Role.READ_ONLY, Role.MEMBER)
    assert not at_least(Role.MEMBER, Role.MAINTAINER)


# --- multi-tenant isolation across every store -----------------------------
def _summary(repo: str = "octo/repo") -> ReviewSummary:
    return ReviewSummary(
        review_id="r1",
        repo=repo,
        pr_number=1,
        head_sha="a" * 40,
        overall=90.0,
        risk={"overall": 90.0},
        blocking=False,
        auto_approved=False,
        tokens=0,
        cost_micros=0,
        latency_ms=0,
    )


def test_every_store_is_tenant_isolated() -> None:
    graph = InMemoryGraphStore()
    graph.record_bug("A", "r", "f.py", 1)
    assert graph.regression_risk("B", "r", "f.py").past_bug_count == 0

    vec = InMemoryVectorStore(HashingEmbedder())
    vec.upsert("A", Collection.SYMBOLS, [VectorRecord("1", "login handler", {})])
    assert vec.search("B", Collection.SYMBOLS, "login") == []

    analytics = InMemoryAnalyticsStore()
    analytics.record("A", _summary())
    assert analytics.repo_overview("B") == []

    audit = HashChainedAuditLog()
    audit.record("A", "alice", "secret.action", {})
    assert audit.list_events("B") == []

    fb = InMemoryFeedbackStore()
    fb.record("A", "r/r", "c", FeedbackAction.ACCEPTED)
    assert fb.stats("B", "r/r") == {}


# --- Postgres RLS coverage -------------------------------------------------
def _load_migration() -> object:
    path = Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0001_initial.py"
    spec = importlib.util.spec_from_file_location("mig_0001", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rls_policies_cover_all_tenant_scoped_tables() -> None:
    """Every table carrying tenant_id must be listed for row-level security in the migration."""
    migration = _load_migration()
    protected = set(migration._TENANT_TABLES)  # type: ignore[attr-defined]
    tenant_tables = {
        name for name, tbl in Base.metadata.tables.items() if "tenant_id" in tbl.columns
    }
    assert protected == tenant_tables
