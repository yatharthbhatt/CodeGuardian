"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import __version__
from app.api.auth import DevTokenVerifier
from app.api.routes import analyze, dashboard, feedback, health, metrics, webhooks
from app.chat.ratelimit import InMemoryRateLimiter
from app.config import Settings, get_settings
from app.core.security.webhook import InMemoryReplayGuard
from app.dashboard.audit import HashChainedAuditLog
from app.dashboard.store import InMemoryAnalyticsStore
from app.feedback.store import InMemoryFeedbackStore
from app.logging_config import configure_logging
from app.memory.graph.inmemory import InMemoryGraphStore
from app.middleware.metrics import MetricsMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.worker.enqueue import build_enqueuer

log = logging.getLogger("codeguardian")
_HOMEPAGE = Path(__file__).parent / "web" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info("starting", extra={"env": settings.environment, "version": __version__})
    yield
    log.info("shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, service_name=settings.service_name)

    app = FastAPI(
        title="CodeGuardian AI",
        version=__version__,
        description="Enterprise-grade multi-agent autonomous code review platform.",
        lifespan=lifespan,
        # Hide interactive docs in production (reduces attack surface).
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    # App-scoped, test-overridable state.
    app.state.settings = settings
    app.state.replay_guard = InMemoryReplayGuard(
        window_seconds=settings.webhook_replay_window_seconds
    )
    app.state.enqueuer = build_enqueuer(settings)
    app.state.feedback_store = InMemoryFeedbackStore()
    # Dashboard + auth stores (Postgres/OIDC-backed in production; in-memory here).
    app.state.token_verifier = DevTokenVerifier()
    app.state.analytics_store = InMemoryAnalyticsStore()
    app.state.audit_store = HashChainedAuditLog()
    app.state.graph_store = InMemoryGraphStore()
    # Rate limiter for the public "try it" analyze endpoints (abuse guard).
    app.state.analyze_limiter = InMemoryRateLimiter(capacity=30, refill_per_sec=1.0)

    # Homepage (public landing + live demo), served by the API itself.
    @app.get("/", include_in_schema=False)
    async def homepage() -> FileResponse:
        return FileResponse(_HOMEPAGE, media_type="text/html")

    # Middleware runs bottom-up: request-id (outermost) → metrics.
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(webhooks.router)
    app.include_router(feedback.router)
    app.include_router(dashboard.router)
    app.include_router(analyze.router)
    return app


# ASGI entrypoint for `uvicorn app.main:app`
app = create_app()
