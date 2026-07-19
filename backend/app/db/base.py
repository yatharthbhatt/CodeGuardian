"""SQLAlchemy declarative base and shared column types."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Consistent constraint naming → clean, reversible Alembic migrations.
_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING)


def uuid_str() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """Marks a table as tenant-scoped.

    Every such table carries a ``tenant_id``. Row-level security policies in the
    migration enforce isolation at the database (PRD §9.2); the repository layer
    enforces it again in application code (defense in depth, testable on SQLite).
    """

    tenant_id: Mapped[str] = mapped_column(nullable=False, index=True)


def json_default() -> dict[str, Any]:
    return {}
