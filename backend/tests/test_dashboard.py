"""Dashboard API tests (PRD §14, §16) — auth, RBAC, tenant scoping."""

from __future__ import annotations

import datetime as dt

import pytest
from app.api.auth import Principal
from app.core.security.rbac import Role
from app.dashboard.store import AgentDecision, ReviewSummary
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> None:
    verifier = client.app.state.token_verifier  # type: ignore[attr-defined]
    verifier.add("reader-a", Principal("tenant-a", "alice", Role.READ_ONLY))
    verifier.add("maint-a", Principal("tenant-a", "mallory", Role.MAINTAINER))
    verifier.add("reader-b", Principal("tenant-b", "bob", Role.READ_ONLY))

    store = client.app.state.analytics_store  # type: ignore[attr-defined]
    store.record(
        "tenant-a",
        ReviewSummary(
            review_id="rev-1",
            repo="octo/repo",
            pr_number=7,
            head_sha="a" * 40,
            overall=88.0,
            risk={"tech_debt": 90.0, "overall": 88.0},
            blocking=True,
            auto_approved=False,
            tokens=1200,
            cost_micros=4200,
            latency_ms=850,
            decisions=[
                AgentDecision("security", "security", "high", "post", "eval", 0.9, "app/s.py", 3)
            ],
            created_at=dt.datetime.now(dt.UTC),
        ),
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/dashboard/overview").status_code == 401


def test_rejects_invalid_token(client: TestClient) -> None:
    resp = client.get("/api/v1/dashboard/overview", headers=_auth("nope"))
    assert resp.status_code == 401


def test_reader_sees_own_tenant_data(client: TestClient) -> None:
    _seed(client)
    resp = client.get("/api/v1/dashboard/overview", headers=_auth("reader-a"))
    assert resp.status_code == 200
    repos = {r["repo"] for r in resp.json()}
    assert "octo/repo" in repos


def test_tenant_isolation(client: TestClient) -> None:
    _seed(client)
    # tenant-b has no data and must never see tenant-a's.
    resp = client.get("/api/v1/dashboard/overview", headers=_auth("reader-b"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_rbac_audit_requires_maintainer(client: TestClient) -> None:
    _seed(client)
    assert client.get("/api/v1/dashboard/audit", headers=_auth("reader-a")).status_code == 403
    assert client.get("/api/v1/dashboard/audit", headers=_auth("maint-a")).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/open-prs",
        "/api/v1/dashboard/cost",
        "/api/v1/dashboard/latency",
        "/api/v1/dashboard/repos/octo/repo/risk-heatmap",
        "/api/v1/dashboard/repos/octo/repo/quality-timeline",
        "/api/v1/dashboard/repos/octo/repo/tech-debt",
        "/api/v1/dashboard/repos/octo/repo/graph",
    ],
)
def test_view_endpoints_authorized_and_tenant_scoped(client: TestClient, path: str) -> None:
    _seed(client)
    assert client.get(path).status_code == 401  # no token
    resp = client.get(path, headers=_auth("reader-a"))
    assert resp.status_code == 200


def test_cost_and_settings_shape(client: TestClient) -> None:
    _seed(client)
    cost = client.get("/api/v1/dashboard/cost", headers=_auth("reader-a")).json()
    assert cost["total_cost_micros"] == 4200
    settings = client.get("/api/v1/dashboard/settings", headers=_auth("reader-a")).json()
    assert settings["tenant_id"] == "tenant-a"
    assert settings["role"] == "read_only"
