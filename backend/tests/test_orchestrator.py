"""LangGraph orchestrator integration tests (PRD §6)."""

from __future__ import annotations

from app.agents.base import AgentContext
from app.domain.findings import Dimension
from app.llm.base import TokenBudget
from app.review.graph import build_graph, run_review
from app.review.state import ReviewState

from tests.conftest import diff_from_added, make_pr

_VULN_LINES = [
    "TOKEN = 'ghp_" + "Q" * 36 + "'",
    "eval(user_input)",
    "def public_api():",
    "    return TOKEN",
]


async def test_run_review_end_to_end_with_fake_provider(router) -> None:  # type: ignore[no-untyped-def]
    pr = make_pr()
    diff = diff_from_added("app/vuln.py", _VULN_LINES)
    result = await run_review(pr, diff, router=router, use_llm=True)

    # Deterministic findings from multiple agents are present.
    dims = {f.dimension for f in result.findings}
    assert Dimension.SECURITY in dims
    assert Dimension.DOCUMENTATION in dims
    # A hardcoded secret + eval → blocking, degraded score.
    assert result.consensus.blocking
    assert result.risk["overall"] < 100.0
    # The fake LLM was actually called (enrichment path ran) and charged the budget.
    assert result.tokens_used > 0
    assert result.errors == []


async def test_run_review_without_llm_is_deterministic(router) -> None:  # type: ignore[no-untyped-def]
    pr = make_pr()
    diff = diff_from_added("app/vuln.py", _VULN_LINES)
    result = await run_review(pr, diff, router=router, use_llm=False)
    assert result.tokens_used == 0  # no LLM calls
    assert any(f.category == "hardcoded-secret" for f in result.findings)


async def test_graceful_degradation_one_agent_fails(router) -> None:  # type: ignore[no-untyped-def]
    class BoomAgent:
        name = "boom"
        dimension = Dimension.PERFORMANCE

        async def run(self, ctx: AgentContext) -> list:  # type: ignore[type-arg]
            raise RuntimeError("kaboom")

    from app.agents.documentation import DocumentationAgent

    budget = TokenBudget(limit=100_000)
    graph = build_graph(router, budget, agents=(BoomAgent(), DocumentationAgent()), use_llm=False)
    state: ReviewState = {
        "pr": make_pr(),
        "diff": diff_from_added("app/d.py", ["def public_api():", "    return 1"]),
        "findings": [],
        "errors": [],
    }
    final = await graph.ainvoke(state)
    # The failing agent is recorded, the healthy agent still produced findings.
    assert any(e["agent"] == "boom" for e in final["errors"])
    assert any(f.category == "missing-docstring" for f in final["findings"])
