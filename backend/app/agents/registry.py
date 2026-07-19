"""Central registry of review agents (PRD §5).

Maps agent name → instance so the Triage/Router can select a subset by name and the
orchestrator can build the graph from that subset. Order here is the canonical order.
"""

from __future__ import annotations

from app.agents.accessibility import AccessibilityAgent
from app.agents.ai_reviewer import AIReviewerAgent
from app.agents.architecture import ArchitectureAgent
from app.agents.base import Agent
from app.agents.devops import DevOpsAgent
from app.agents.documentation import DocumentationAgent
from app.agents.performance import PerformanceAgent
from app.agents.security import SecurityAgent
from app.agents.testing import TestingAgent

ALL_AGENTS: dict[str, Agent] = {
    a.name: a
    for a in (
        SecurityAgent(),
        ArchitectureAgent(),
        PerformanceAgent(),
        TestingAgent(),
        DevOpsAgent(),
        AccessibilityAgent(),
        DocumentationAgent(),
        AIReviewerAgent(),
    )
}


def agents_for(names: list[str]) -> tuple[Agent, ...]:
    """Return agent instances for ``names`` in canonical order (unknown names ignored)."""
    return tuple(ALL_AGENTS[n] for n in ALL_AGENTS if n in set(names))
