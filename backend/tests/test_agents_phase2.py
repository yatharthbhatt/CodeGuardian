"""Detection tests for the 5 Phase-2 agents (PRD §5)."""

from __future__ import annotations

from app.agents.accessibility import AccessibilityAgent
from app.agents.ai_reviewer import AIReviewerAgent
from app.agents.base import AgentContext
from app.agents.devops import DevOpsAgent
from app.agents.performance import PerformanceAgent
from app.agents.testing import TestingAgent
from app.domain.findings import Dimension
from app.llm.base import TokenBudget
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.review.diff import FileDiff, NormalizedDiff

from tests.conftest import diff_from_added, make_pr


def _ctx(path: str, lines: list[str]) -> AgentContext:
    return AgentContext(pr=make_pr(), diff=diff_from_added(path, lines), router=None)


def _multi_ctx(files: list[tuple[str, list[str]]]) -> AgentContext:
    from app.review.diff import AddedLine

    fdiffs = [
        FileDiff(path=p, added=[AddedLine(new_line=i + 1, text=t) for i, t in enumerate(ls)])
        for p, ls in files
    ]
    return AgentContext(pr=make_pr(), diff=NormalizedDiff(files=fdiffs), router=None)


# --- Performance ----------------------------------------------------------
async def test_performance_detects_n_plus_one() -> None:
    findings = await PerformanceAgent().run(
        _ctx("app/s.py", ["for u in users:", "    p = db.query(Profile).get(u.id)"])
    )
    assert any(f.category == "n-plus-one-query" for f in findings)


async def test_performance_detects_select_star_and_blocking_io() -> None:
    findings = await PerformanceAgent().run(
        _ctx("app/s.py", ["rows = conn.exec('SELECT * FROM t')", "requests.get(url)"])
    )
    cats = {f.category for f in findings}
    assert "select-star" in cats
    assert "blocking-io-in-async" in cats


# --- Testing --------------------------------------------------------------
async def test_testing_flags_code_without_tests() -> None:
    findings = await TestingAgent().run(_ctx("app/feature.py", ["def f():", "    return 1"]))
    assert any(f.category == "missing-tests" for f in findings)


async def test_testing_ok_when_tests_present() -> None:
    ctx = _multi_ctx(
        [
            ("app/feature.py", ["def f(): return 1"]),
            ("tests/test_feature.py", ["def test_f(): pass"]),
        ]
    )
    findings = await TestingAgent().run(ctx)
    assert not any(f.category == "missing-tests" for f in findings)


# --- DevOps ---------------------------------------------------------------
async def test_devops_flags_unpinned_base_image() -> None:
    findings = await DevOpsAgent().run(_ctx("Dockerfile", ["FROM python:latest"]))
    assert any(f.category == "docker-unpinned-base" for f in findings)


async def test_devops_flags_open_ingress_in_terraform() -> None:
    findings = await DevOpsAgent().run(_ctx("infra/net.tf", ['cidr_blocks = ["0.0.0.0/0"]']))
    assert any(f.category == "open-ingress" for f in findings)


async def test_devops_ignores_application_code() -> None:
    # The unpinned-base regex must not fire on ordinary Python.
    findings = await DevOpsAgent().run(_ctx("app/s.py", ["FROM = 'python:latest'"]))
    assert findings == []


# --- Accessibility --------------------------------------------------------
async def test_accessibility_flags_img_without_alt() -> None:
    findings = await AccessibilityAgent().run(
        _ctx("web/Card.tsx", ["return <img src='/logo.png' />"])
    )
    assert any(f.category == "img-missing-alt" for f in findings)


async def test_accessibility_ok_with_alt() -> None:
    findings = await AccessibilityAgent().run(
        _ctx("web/Card.tsx", ["return <img src='/logo.png' alt='Logo' />"])
    )
    assert not any(f.category == "img-missing-alt" for f in findings)


# --- AI Reviewer (correctness, LLM-only) ----------------------------------
async def test_ai_reviewer_produces_correctness_finding_from_llm() -> None:
    provider = FakeProvider()
    provider.set_findings(
        [
            {
                "category": "logic-error",
                "severity": "high",
                "confidence": 0.8,
                "title": "Off-by-one in pagination",
                "message": "The loop skips the last page.",
                "file_path": "app/s.py",
                "line": 1,
                "why": "Range excludes the final element.",
                "impact": "Missing data for users.",
            }
        ]
    )
    ctx = AgentContext(
        pr=make_pr(),
        diff=diff_from_added("app/s.py", ["for i in range(0, n-1):"]),
        router=LLMRouter(provider),
        budget=TokenBudget(limit=100_000),
    )
    findings = await AIReviewerAgent().run(ctx)
    assert findings
    assert findings[0].dimension is Dimension.CORRECTNESS
    assert findings[0].confidence <= 0.9  # LLM-only claims are capped


async def test_ai_reviewer_no_llm_is_silent() -> None:
    findings = await AIReviewerAgent().run(_ctx("app/s.py", ["for i in range(0, n-1):"]))
    assert findings == []
