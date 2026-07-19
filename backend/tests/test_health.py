from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200


def test_request_id_header_echoed(client: TestClient) -> None:
    resp = client.get("/healthz", headers={"X-Request-ID": "abc12345"})
    assert resp.headers["X-Request-ID"] == "abc12345"


def test_request_id_minted_when_absent(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert len(resp.headers["X-Request-ID"]) >= 8


def test_hostile_request_id_is_rejected_and_replaced(client: TestClient) -> None:
    # A header with a newline must never be reflected verbatim (log-injection guard).
    resp = client.get("/healthz", headers={"X-Request-ID": "bad\nvalue"})
    assert "\n" not in resp.headers["X-Request-ID"]
