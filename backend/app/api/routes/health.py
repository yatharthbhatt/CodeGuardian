"""Liveness/readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    """Readiness probe.

    Phase 0 reports process readiness only. Dependency checks (DB/Redis/Neo4j/Qdrant)
    are added as those integrations land so we never report ready while a hard
    dependency is down.
    """
    return {"status": "ready"}
