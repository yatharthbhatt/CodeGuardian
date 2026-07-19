"""Prometheus scrape endpoint (PRD §13).

Exposition-format metrics for Prometheus. This endpoint should be network-restricted to
the monitoring system in production (it exposes only counts/labels — never secrets/PII).
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.observability import metrics

router = APIRouter(tags=["observability"])

_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    return Response(content=metrics.render(), media_type=_CONTENT_TYPE)
