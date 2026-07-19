"""Homepage + public analyze endpoints (the 'try it' demo)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_VULN = "\n".join(
    [
        "API_TOKEN = 'ghp_" + "F" * 34 + "'",
        "import hashlib",
        "def login(u, p):",
        "    return hashlib.md5(p.encode()).hexdigest()",
        "x = eval(user_input)",
    ]
)


def test_homepage_served(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "CodeGuardian" in resp.text


def test_analyze_code_finds_vulnerabilities(client: TestClient) -> None:
    resp = client.post("/api/v1/analyze/code", json={"filename": "app.py", "code": _VULN})
    assert resp.status_code == 200
    data = resp.json()
    cats = {f["category"] for f in data["findings"]}
    assert "hardcoded-secret" in cats
    assert "dangerous-eval" in cats
    assert "weak-hash" in cats
    assert data["verdict"] == "REQUEST_CHANGES"
    assert data["counts"]["fixes"] >= 1  # md5 → sha256 suggestion
    # A weak-hash finding carries a before/after suggestion.
    wh = next(f for f in data["findings"] if f["category"] == "weak-hash")
    assert wh["suggestion"]["fixed"].strip()


def test_analyze_code_clean_snippet(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/analyze/code",
        json={"filename": "ok.py", "code": '"""Doc."""\nX = 1\n'},
    )
    assert resp.status_code == 200
    security = [f for f in resp.json()["findings"] if f["dimension"] == "security"]
    assert security == []


def test_analyze_code_empty_rejected(client: TestClient) -> None:
    assert client.post("/api/v1/analyze/code", json={"code": "   "}).status_code == 400


def test_analyze_pr_rejects_non_github_url_ssrf(client: TestClient) -> None:
    # SSRF guard: only github.com PR URLs are accepted.
    for url in ["http://169.254.169.254/latest/meta-data", "https://evil.com/pull/1", "not a url"]:
        resp = client.post("/api/v1/analyze/pr", json={"url": url})
        assert resp.status_code == 400
