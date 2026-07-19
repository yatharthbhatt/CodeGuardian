"""Dashboard API (PRD §14, §16).

All endpoints require an authenticated principal (bearer/OIDC) with at least the
``read_only`` role, and are **tenant-scoped from the token** — the tenant is never taken
from a query parameter, so a caller can only ever see their own tenant's data.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request

from app.api.auth import Principal, require_role
from app.core.security.rbac import Role

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# Most routes need read-only; sensitive views (audit) need maintainer+ (RBAC).
_Reader = Annotated[Principal, Depends(require_role(Role.READ_ONLY))]
_Maintainer = Annotated[Principal, Depends(require_role(Role.MAINTAINER))]
_Repo = Annotated[str, Path(pattern=r"^[^/]+/[^/]+$", max_length=512)]


def _analytics(request: Request) -> Any:
    return request.app.state.analytics_store


def _audit(request: Request) -> Any:
    return request.app.state.audit_store


def _graph(request: Request) -> Any:
    return request.app.state.graph_store


@router.get("/overview")
async def overview(request: Request, principal: _Reader) -> list[dict[str, Any]]:
    return _analytics(request).repo_overview(principal.tenant_id)  # type: ignore[no-any-return]


@router.get("/open-prs")
async def open_prs(request: Request, principal: _Reader) -> list[dict[str, Any]]:
    return _analytics(request).open_prs(principal.tenant_id)  # type: ignore[no-any-return]


@router.get("/repos/{owner}/{name}/risk-heatmap")
async def risk_heatmap(
    request: Request, owner: str, name: str, principal: _Reader
) -> list[dict[str, Any]]:
    return _analytics(request).risk_heatmap(principal.tenant_id, f"{owner}/{name}")  # type: ignore[no-any-return]


@router.get("/reviews/{review_id}/agents")
async def agent_decisions(
    request: Request, review_id: str, principal: _Reader
) -> list[dict[str, Any]]:
    return _analytics(request).agent_decisions(principal.tenant_id, review_id)  # type: ignore[no-any-return]


@router.get("/cost")
async def cost(request: Request, principal: _Reader) -> dict[str, Any]:
    return _analytics(request).cost_analytics(principal.tenant_id)  # type: ignore[no-any-return]


@router.get("/latency")
async def latency(request: Request, principal: _Reader) -> dict[str, Any]:
    return _analytics(request).latency(principal.tenant_id)  # type: ignore[no-any-return]


@router.get("/repos/{owner}/{name}/quality-timeline")
async def quality_timeline(
    request: Request, owner: str, name: str, principal: _Reader
) -> list[dict[str, Any]]:
    return _analytics(request).quality_timeline(principal.tenant_id, f"{owner}/{name}")  # type: ignore[no-any-return]


@router.get("/repos/{owner}/{name}/tech-debt")
async def tech_debt(request: Request, owner: str, name: str, principal: _Reader) -> dict[str, Any]:
    return _analytics(request).tech_debt(principal.tenant_id, f"{owner}/{name}")  # type: ignore[no-any-return]


@router.get("/repos/{owner}/{name}/graph")
async def knowledge_graph(
    request: Request, owner: str, name: str, principal: _Reader
) -> dict[str, Any]:
    return _graph(request).graph_export(principal.tenant_id, f"{owner}/{name}")  # type: ignore[no-any-return]


@router.get("/audit")
async def audit_log(request: Request, principal: _Maintainer) -> list[dict[str, Any]]:
    return _audit(request).list_events(principal.tenant_id)  # type: ignore[no-any-return]


@router.get("/settings")
async def settings(request: Request, principal: _Reader) -> dict[str, Any]:
    # Echoes the caller's own scope (never another tenant's).
    return {"tenant_id": principal.tenant_id, "role": principal.role.value, "user": principal.user}
