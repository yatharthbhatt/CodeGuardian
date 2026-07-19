"""Triage/Router tests (PRD §5.9) — the cost/latency optimizer."""

from __future__ import annotations

from app.review.triage import triage

from tests.conftest import diff_from_added, make_pr


def _route(path: str, lines: list[str]):  # type: ignore[no-untyped-def]
    return triage(make_pr(), diff_from_added(path, lines))


def test_backend_python_selects_backend_agents_not_frontend_or_infra() -> None:
    d = _route("app/service.py", ["def f():", "    return db.query(X).all()"])
    assert {
        "security",
        "ai_reviewer",
        "architecture",
        "documentation",
        "testing",
        "performance",
    } <= set(d.selected)
    assert "accessibility" not in d.selected
    assert "devops" not in d.selected
    # Every selected agent carries a human-readable reason.
    assert all(name in d.reasons for name in d.selected)


def test_frontend_selects_accessibility() -> None:
    d = _route("web/Button.tsx", ["export const B = () => <img src='x' />"])
    assert "accessibility" in d.selected
    assert d.classification.is_frontend


def test_infra_selects_devops() -> None:
    d = _route("Dockerfile", ["FROM python:latest", "RUN echo hi"])
    assert "devops" in d.selected
    assert d.classification.is_infra


def test_docs_only_is_trivial_and_auto_approve_eligible() -> None:
    d = _route("README.md", ["# Title", "some docs"])
    assert d.classification.only_docs
    assert d.is_trivial
    assert d.auto_approve_eligible
    # Docs PRs don't need the correctness/perf agents.
    assert "ai_reviewer" not in d.selected
    assert "performance" not in d.selected
    assert set(d.selected) == {"security", "documentation"}


def test_lockfile_bump_is_auto_approve_eligible() -> None:
    d = _route("poetry.lock", ["some-package = 1.2.3"])
    assert d.classification.only_lockfiles
    assert d.auto_approve_eligible


def test_large_backend_change_is_not_trivial() -> None:
    d = _route("app/big.py", [f"x{i} = {i}" for i in range(50)])
    assert not d.is_trivial
    assert not d.auto_approve_eligible


def test_routing_decision_serializes() -> None:
    d = _route("app/service.py", ["x = 1"])
    payload = d.to_dict()
    assert set(payload) >= {
        "selected",
        "reasons",
        "is_trivial",
        "auto_approve_eligible",
        "classification",
    }
