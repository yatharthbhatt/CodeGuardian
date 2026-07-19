"""Structural tenant-isolation invariant (PRD §9.2).

This guards the *shape* of the schema: every business/tenant table must carry a
``tenant_id`` column so RLS + app-layer scoping can apply. If someone adds a new
tenant-scoped table without tenant_id, this test fails. (Runtime RLS enforcement is
exercised against Postgres in the Phase 6 hardening suite.)
"""

from __future__ import annotations

from app.db import models  # noqa: F401  registers all tables on Base.metadata
from app.db.base import Base

# Global reference tables that are intentionally NOT tenant-scoped.
_GLOBAL_TABLES = {"tenants", "users"}


def test_all_business_tables_have_tenant_id() -> None:
    missing: list[str] = []
    for name, table in Base.metadata.tables.items():
        if name in _GLOBAL_TABLES:
            continue
        if "tenant_id" not in table.columns:
            missing.append(name)
    assert not missing, f"tenant-scoped tables missing tenant_id: {missing}"


def test_expected_core_tables_exist() -> None:
    expected = {
        "tenants",
        "users",
        "memberships",
        "installations",
        "repositories",
        "pull_requests",
        "reviews",
        "findings",
        "patches",
        "risk_scorecards",
        "feedback",
        "budgets",
        "audit_events",
    }
    assert expected.issubset(set(Base.metadata.tables))
