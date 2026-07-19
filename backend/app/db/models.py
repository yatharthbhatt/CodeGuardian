"""Core data model (PRD §10).

All business tables are tenant-scoped. ``audit_events`` is append-only and
hash-chained (PRD §9.8) so tampering is detectable.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, uuid_str


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    github_account: Mapped[str | None] = mapped_column(String(255), unique=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320))


class Membership(Base, TimestampMixin, TenantScopedMixin):
    """RBAC edge between a user and a tenant (PRD §9.2)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    # owner | admin | maintainer | member | read_only | service
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")


class Installation(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    github_installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)


class Repository(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    github_repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)

    pull_requests: Mapped[list[PullRequest]] = relationship(back_populates="repository")


class PullRequest(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repo_id", "number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    repo_id: Mapped[str] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(2000), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    author_login: Mapped[str] = mapped_column(String(255), nullable=False)

    repository: Mapped[Repository] = relationship(back_populates="pull_requests")
    reviews: Mapped[list[Review]] = relationship(back_populates="pull_request")


class Review(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    pr_id: Mapped[str] = mapped_column(ForeignKey("pull_requests.id"), nullable=False)
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    model_used: Mapped[str | None] = mapped_column(String(128))
    cost_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Idempotency: one review per (pr, head_sha, delivery) — set from the webhook.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    findings: Mapped[list[Finding]] = relationship(back_populates="review")
    pull_request: Mapped[PullRequest] = relationship(back_populates="reviews")


class Finding(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    # severity ∈ {info, low, medium, high, critical}
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    cwe: Mapped[str | None] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    line: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Explainability (PRD §8.5): why/impact/alternative/references/complexity/confidence
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    review: Mapped[Review] = relationship(back_populates="findings")


class Patch(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "patches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), nullable=False)
    unified_diff: Mapped[str] = mapped_column(Text, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)


class RiskScorecard(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "risk_scorecards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), nullable=False, unique=True)
    security: Mapped[float] = mapped_column(Float, default=0.0)
    architecture: Mapped[float] = mapped_column(Float, default=0.0)
    performance: Mapped[float] = mapped_column(Float, default=0.0)
    maintainability: Mapped[float] = mapped_column(Float, default=0.0)
    tech_debt: Mapped[float] = mapped_column(Float, default=0.0)
    documentation: Mapped[float] = mapped_column(Float, default=0.0)
    overall: Mapped[float] = mapped_column(Float, default=0.0)


class Feedback(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # accepted|rejected|edited
    actor_login: Mapped[str] = mapped_column(String(255), nullable=False)


class Budget(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. 2026-07
    tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_used_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    ceiling_micros: Mapped[int] = mapped_column(BigInteger, default=0)


class AuditEvent(Base):
    """Append-only, hash-chained audit log (PRD §9.8).

    ``payload_hash`` = sha256(canonical(payload)); ``prev_hash`` links to the prior
    event for this tenant, making silent deletion/reordering detectable.
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
