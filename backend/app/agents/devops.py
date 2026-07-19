"""DevOps Agent (PRD §5.6).

Deterministic checks for Dockerfile/IaC/CI hygiene + LLM suggestions. Rules are matched
against the relevant file kind (Dockerfile, Terraform, YAML/CI) so they don't fire on
application code.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.agents.base import (
    AgentContext,
    DeterministicRule,
    run_llm_enrichment,
    scan_rules,
)
from app.domain.findings import Dimension, Finding, Severity
from app.review.diff import FileDiff, NormalizedDiff

_SYSTEM = (
    "You are a DevOps/platform engineer. Review Dockerfiles, Kubernetes/Terraform, CI, and "
    "environment configuration for security and reliability issues. Only report issues in the diff."
)


def _is_dockerfile(f: FileDiff) -> bool:
    base = f.path.rsplit("/", 1)[-1]
    return base == "Dockerfile" or base.endswith(".Dockerfile") or base.startswith("Dockerfile")


def _is_infra(f: FileDiff) -> bool:
    return f.language in {"yaml", "terraform"} or ".github/workflows" in f.path or _is_dockerfile(f)


_DOCKER_RULES: list[DeterministicRule] = [
    DeterministicRule(
        category="docker-unpinned-base",
        severity=Severity.MEDIUM,
        pattern=re.compile(r"^\s*FROM\s+\S+:latest|^\s*FROM\s+[^\s:@]+\s*$"),
        title="Unpinned container base image",
        why="Using :latest or no tag makes builds non-reproducible and can pull vulnerable images.",
        impact="Supply-chain drift and unexpected breakage.",
        alternative="Pin a specific version/digest (FROM image@sha256:...).",
        cwe="CWE-1104",
    ),
    DeterministicRule(
        category="docker-curl-pipe-sh",
        severity=Severity.HIGH,
        pattern=re.compile(r"curl[^\n]*\|\s*(sudo\s+)?(sh|bash)"),
        title="Piping curl output straight into a shell",
        why="Executing remote scripts unverified is a supply-chain risk.",
        impact="Arbitrary code execution at build time.",
        alternative="Download, verify a checksum/signature, then execute.",
        cwe="CWE-494",
    ),
]

_INFRA_RULES: list[DeterministicRule] = [
    DeterministicRule(
        category="open-ingress",
        severity=Severity.HIGH,
        pattern=re.compile(r"0\.0\.0\.0/0|::/0"),
        title="Network open to the entire internet (0.0.0.0/0)",
        why="Unrestricted ingress exposes services to the whole internet.",
        impact="Broad attack surface / data exposure.",
        alternative="Restrict CIDR ranges to known sources.",
        cwe="CWE-284",
    ),
    DeterministicRule(
        category="privileged-container",
        severity=Severity.HIGH,
        pattern=re.compile(r"privileged:\s*true"),
        title="Privileged container",
        why="Privileged containers can escape isolation and access the host.",
        impact="Host compromise from a container breakout.",
        alternative="Drop privileges; grant only required capabilities.",
        cwe="CWE-250",
    ),
]


def _subset(ctx: AgentContext, predicate: Callable[[FileDiff], bool]) -> NormalizedDiff:
    return NormalizedDiff(files=[f for f in ctx.diff.files if predicate(f)])


class DevOpsAgent:
    name = "devops"
    dimension = Dimension.DEVOPS

    async def run(self, ctx: AgentContext) -> list[Finding]:
        # Restrict each rule set to the files it applies to (Dockerfile vs infra).
        findings = scan_rules(
            _subset(ctx, _is_dockerfile), _DOCKER_RULES, agent=self.name, dimension=self.dimension
        )
        findings.extend(
            scan_rules(
                _subset(ctx, _is_infra), _INFRA_RULES, agent=self.name, dimension=self.dimension
            )
        )
        findings.extend(
            await run_llm_enrichment(
                ctx,
                agent=self.name,
                dimension=self.dimension,
                system=_SYSTEM,
                instruction="List DevOps/infrastructure issues in this diff.",
            )
        )
        return findings
