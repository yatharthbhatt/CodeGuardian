"""LangGraph orchestrator (PRD §6).

Topology:  START ─▶ {security ∥ architecture ∥ documentation} ─▶ aggregate ─▶ END

The three agents run as parallel branches (fan-out) and merge their findings via the
``operator.add`` reducer on ``ReviewState.findings``. The ``aggregate`` node fans in,
builds weighted consensus and the risk scorecard. Every agent node is wrapped so a single
agent failure is recorded and skipped rather than failing the whole review (rule #9).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.architecture import ArchitectureAgent
from app.agents.base import Agent, AgentContext
from app.agents.documentation import DocumentationAgent
from app.agents.registry import agents_for
from app.agents.security import SecurityAgent
from app.domain.explainability import enforce_explainability
from app.domain.findings import Finding
from app.llm.base import TokenBudget
from app.llm.router import LLMRouter
from app.memory.service import RepositoryMemory
from app.memory.types import MemoryContext
from app.observability import metrics
from app.observability.tracing import span
from app.patch.generator import SuggestedPatch, generate_patches
from app.review.consensus import ConsensusResult, build_consensus
from app.review.diff import NormalizedDiff
from app.review.scoring import build_scorecard
from app.review.state import PRMeta, ReviewState
from app.review.triage import RoutingDecision, triage

log = logging.getLogger("codeguardian.orchestrator")

_DEFAULT_AGENTS: tuple[Agent, ...] = (
    SecurityAgent(),
    ArchitectureAgent(),
    DocumentationAgent(),
)


@dataclass
class ReviewResult:
    pr: PRMeta
    findings: list[Finding]
    consensus: ConsensusResult
    risk: dict[str, float]
    tokens_used: int
    errors: list[dict[str, str]] = field(default_factory=list)
    routing: RoutingDecision | None = None
    auto_approved: bool = False
    memory_context: MemoryContext | None = None
    patches: list[SuggestedPatch] = field(default_factory=list)
    cost_micros: int = 0
    cost_by_agent: dict[str, int] = field(default_factory=dict)


def _make_agent_node(
    agent: Agent, ctx_factory: Callable[[ReviewState], AgentContext]
) -> Callable[[ReviewState], Awaitable[dict[str, Any]]]:
    async def node(state: ReviewState) -> dict[str, Any]:
        ctx: AgentContext = ctx_factory(state)
        start = time.perf_counter()
        try:
            with span("agent.run", agent=agent.name):
                findings = await agent.run(ctx)
            metrics.AGENT_RUNS.labels(agent.name, "success").inc()
            return {"findings": findings}
        except Exception as exc:
            metrics.AGENT_RUNS.labels(agent.name, "error").inc()
            log.exception("agent failed", extra={"agent": agent.name})
            return {"errors": [{"agent": agent.name, "error": type(exc).__name__}]}
        finally:
            metrics.AGENT_LATENCY.labels(agent.name).observe(time.perf_counter() - start)

    return node


async def _aggregate_node(state: ReviewState) -> dict[str, Any]:
    findings = state.get("findings", [])
    consensus = build_consensus(findings)
    risk = build_scorecard(findings)
    return {"consensus": consensus.to_dict(), "risk": risk}


def build_graph(
    router: LLMRouter | None,
    budget: TokenBudget,
    *,
    agents: tuple[Agent, ...] = _DEFAULT_AGENTS,
    checkpointer: Any = None,
    use_llm: bool = True,
    memory: MemoryContext | None = None,
) -> Any:
    """Compile the review graph. ``checkpointer`` persists state to Postgres in prod."""

    def ctx_factory(state: ReviewState) -> AgentContext:
        return AgentContext(
            pr=state["pr"],
            diff=state["diff"],
            router=router,
            budget=budget,
            use_llm=use_llm and router is not None,
            memory=memory,
        )

    builder = StateGraph(ReviewState)
    for agent in agents:
        builder.add_node(agent.name, _make_agent_node(agent, ctx_factory))
        builder.add_edge(START, agent.name)
        builder.add_edge(agent.name, "aggregate")
    builder.add_node("aggregate", _aggregate_node)
    builder.add_edge("aggregate", END)
    return builder.compile(checkpointer=checkpointer)


async def run_review(
    pr: PRMeta,
    diff: NormalizedDiff,
    *,
    router: LLMRouter | None = None,
    token_budget: int = 120_000,
    use_llm: bool = True,
    checkpointer: Any = None,
    thread_id: str | None = None,
    agents: tuple[Agent, ...] | None = None,
    memory: RepositoryMemory | None = None,
    consensus_adjustments: dict[str, float] | None = None,
) -> ReviewResult:
    """Run the full review and return a rich result for publishing.

    When ``agents`` is not given, the Triage/Router selects the minimal set to run
    (cost/latency saver) and decides auto-approve eligibility. When ``memory`` is given,
    repository memory feeds context to the agents and contributes blast-radius/regression
    findings, and the graph is updated with this PR afterwards.
    """
    routing: RoutingDecision | None = None
    if agents is None:
        routing = triage(pr, diff)
        agents = agents_for(routing.selected)

    mem_context: MemoryContext | None = None
    mem_facts = None
    if memory is not None:
        # Add this PR's structure first so blast-radius/cycles reflect the current change.
        mem_facts = memory.update_structure(pr, diff)
        mem_context = memory.context_for(pr, diff)

    budget = TokenBudget(limit=token_budget)
    graph = build_graph(
        router,
        budget,
        agents=agents,
        checkpointer=checkpointer,
        use_llm=use_llm,
        memory=mem_context,
    )

    initial: ReviewState = {"pr": pr, "diff": diff, "findings": [], "errors": []}
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    review_start = time.perf_counter()
    with span("review", repo=pr.repo_full_name, pr=pr.number):
        final: ReviewState = await graph.ainvoke(initial, config=config)

    agent_findings = final.get("findings", [])
    # Repository memory contributes derived findings (blast radius, regression risk).
    insight_findings = (
        memory.insights(mem_context) if (memory is not None and mem_context is not None) else []
    )
    findings = agent_findings + insight_findings
    # Guarantee every finding carries the full explainability payload (PRD §8.5).
    enforce_explainability(findings)

    # Rebuild the rich ConsensusResult for the publisher (recompute to include insights).
    # Golden-Path adjustments down-weight categories the team routinely rejects.
    consensus = build_consensus(findings, consensus_adjustments)
    risk = build_scorecard(findings)
    # Auto-patch: generate validated fix suggestions for mechanically-fixable findings.
    patches = generate_patches(findings, diff)
    # Confidence-gated auto-approve: only for eligible trivial PRs with a fully clean review.
    auto_approved = bool(
        routing
        and routing.auto_approve_eligible
        and not consensus.blocking
        and not consensus.posted
    )

    # Update the graph/vector store with this PR so future reviews are smarter.
    if memory is not None:
        memory.record_outcome(pr, diff, agent_findings, mem_facts)

    metrics.REVIEW_LATENCY.observe(time.perf_counter() - review_start)
    metrics.REVIEWS.labels("success").inc()

    return ReviewResult(
        pr=pr,
        findings=findings,
        consensus=consensus,
        risk=risk,
        tokens_used=budget.used,
        errors=final.get("errors", []),
        routing=routing,
        auto_approved=auto_approved,
        memory_context=mem_context,
        patches=patches,
        cost_micros=budget.cost_micros,
        cost_by_agent=budget.cost_by_agent(),
    )
