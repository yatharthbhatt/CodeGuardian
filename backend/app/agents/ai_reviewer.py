"""AI Reviewer Agent (PRD §5.8) — the unique one.

Not a linter. It reads the PR intent (title/body/linked issue) and the diff and asks the
question no static tool can: *does this code actually solve the stated problem?* It looks
for logic errors, wrong edge handling, silent behavior changes, and mismatches between the
stated intent and the implementation.

This agent is LLM-only (no deterministic rules), so its findings are capped-confidence and,
like all LLM output, strictly validated and constrained to files in the diff before use.
When no LLM is configured it simply contributes nothing (graceful).
"""

from __future__ import annotations

from app.agents.base import AgentContext, run_llm_enrichment
from app.domain.findings import Dimension, Finding

_SYSTEM = (
    "You are a staff engineer doing a correctness review. Compare the PR's stated intent "
    "(title/description) against the actual diff. Identify: logic errors, off-by-one and "
    "boundary mistakes, unhandled edge cases, error paths that swallow failures, behavior "
    "changes not reflected in the description, and cases where the implementation does not "
    "actually satisfy the stated goal. Do NOT report style or formatting. Only report issues "
    "you can justify from the diff, and prefer a few high-value findings over many nitpicks."
)


class AIReviewerAgent:
    name = "ai_reviewer"
    dimension = Dimension.CORRECTNESS

    async def run(self, ctx: AgentContext) -> list[Finding]:
        return await run_llm_enrichment(
            ctx,
            agent=self.name,
            dimension=self.dimension,
            system=_SYSTEM,
            instruction=(
                "Does this change correctly and completely solve the problem described in the "
                "PR? List concrete correctness issues."
            ),
        )
