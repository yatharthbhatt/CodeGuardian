"""initial schema + row-level security

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-07

Baseline schema for the core tables (PRD §10). Tables are created from the SQLAlchemy
metadata (single source of truth). On PostgreSQL we then enable **row-level security**
(PRD §9.2): every tenant-scoped table only exposes rows whose ``tenant_id`` matches the
``app.current_tenant`` GUC set per request (see app/db/session.py::set_tenant_context).
On SQLite (tests) the RLS block is skipped; application-layer scoping still applies.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.db import models  # noqa: F401  registers tables
from app.db.base import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that carry tenant_id and must be protected by RLS.
_TENANT_TABLES = (
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
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    if bind.dialect.name != "postgresql":
        return

    # Enable + force RLS and add a tenant-isolation policy on each protected table.
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.current_tenant', true))
            WITH CHECK (tenant_id = current_setting('app.current_tenant', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _TENANT_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    Base.metadata.drop_all(bind=bind)
