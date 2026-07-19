"""Testing Agent (PRD §5.5).

Diff-level heuristic: production code changed but no tests were added/changed → flag it.
Plus per-line smells (assertion-free tests) and LLM suggestions for edge/property tests.
"""

from __future__ import annotations

import re

from app.agents.base import AgentContext, run_llm_enrichment
from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    Severity,
)

_SYSTEM = (
    "You are a test engineer. Identify missing unit/integration tests, untested edge cases, "
    "and weak assertions introduced by this diff. Suggest concrete test cases."
)

_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(_test|\.test|\.spec|test_)")
_CODE_EXT = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".rs")


def _is_test_file(path: str) -> bool:
    return bool(_TEST_PATH.search(path))


def _is_production_code(path: str) -> bool:
    return path.endswith(_CODE_EXT) and not _is_test_file(path)


class TestingAgent:
    name = "testing"
    dimension = Dimension.TESTING

    async def run(self, ctx: AgentContext) -> list[Finding]:
        findings: list[Finding] = []
        prod_files = [f for f in ctx.diff.files if _is_production_code(f.path)]
        test_files = [f for f in ctx.diff.files if _is_test_file(f.path)]
        if prod_files and not test_files:
            first = prod_files[0]
            findings.append(
                Finding(
                    agent=self.name,
                    dimension=self.dimension,
                    category="missing-tests",
                    severity=Severity.MEDIUM,
                    confidence=0.7,
                    title="Production code changed without accompanying tests",
                    message=(
                        f"{len(prod_files)} code file(s) changed (e.g. {first.path}) but no "
                        "test files were added or modified."
                    ),
                    file_path=first.path,
                    line=first.added[0].new_line if first.added else None,
                    source=FindingSource.DETERMINISTIC,
                    explanation=Explanation(
                        why="Untested changes are the leading source of regressions.",
                        impact="Higher escaped-defect rate; risky refactors.",
                        alternative="Add unit tests for the new/changed behavior and edge cases.",
                        complexity="medium",
                    ),
                )
            )
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List missing tests and edge cases for this diff.",
            )
        )
        return findings
