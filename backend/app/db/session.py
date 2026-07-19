"""Database engine/session factory.

The engine is built from ``settings.database_url`` (a DSN whose credentials come from
the secret manager — never hardcoded). Tenant scoping is enforced by the repository
layer plus Postgres RLS; see ``set_tenant_context`` for how a request binds its tenant.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

_engine: Engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)


def get_engine() -> Engine:
    return _engine


def set_tenant_context(session: Session, tenant_id: str) -> None:
    """Bind the tenant for Postgres row-level security.

    RLS policies read ``current_setting('app.current_tenant')`` (see the migration).
    On SQLite (tests) this is a harmless no-op; app-layer scoping still applies.
    """
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_tenant', :tid, true)"),
            {"tid": tenant_id},
        )


@contextmanager
def session_scope(tenant_id: str | None = None) -> Iterator[Session]:
    """Transactional session scope, optionally bound to a tenant."""
    session = SessionLocal()
    try:
        if tenant_id is not None:
            set_tenant_context(session, tenant_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
