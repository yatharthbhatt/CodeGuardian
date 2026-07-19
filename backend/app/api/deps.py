"""FastAPI dependencies (shared, testable providers)."""

from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.core.security.webhook import ReplayGuard
from app.feedback.store import FeedbackStore
from app.worker.enqueue import Enqueuer


def get_settings_dep(request: Request) -> Settings:
    """Return the app-scoped Settings (overridable in tests via app.state)."""
    return request.app.state.settings  # type: ignore[no-any-return]


def get_replay_guard(request: Request) -> ReplayGuard:
    """Return the app-scoped replay guard."""
    return request.app.state.replay_guard  # type: ignore[no-any-return]


def get_enqueuer(request: Request) -> Enqueuer:
    """Return the app-scoped review enqueuer."""
    return request.app.state.enqueuer  # type: ignore[no-any-return]


def get_feedback_store(request: Request) -> FeedbackStore:
    """Return the app-scoped feedback store."""
    return request.app.state.feedback_store  # type: ignore[no-any-return]
