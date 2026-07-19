"""Triage / Router (PRD §5.9, §8.16) — cost & latency optimizer.

Classifies the diff (languages, surfaces touched, size) and selects the *minimal* set of
agents worth running, so we don't run the Accessibility agent on a backend-only Go PR or
the DevOps agent on a docs change. Also decides whether a PR is trivial and eligible for a
confidence-gated auto-approve (final approval still requires a clean review).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.review.diff import FileDiff, NormalizedDiff
from app.review.state import PRMeta

_FRONTEND_LANGS = {"javascript", "typescript", "html", "css"}
_BACKEND_LANGS = {
    "python",
    "javascript",
    "typescript",
    "go",
    "ruby",
    "java",
    "rust",
    "php",
    "csharp",
    "sql",
}
_DOCS_LANGS = {"markdown"}
_INFRA_LANGS = {"yaml", "terraform"}

_LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "requirements.txt",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
}
# A trivial diff is at most this many added lines (when it's not docs-only).
_TRIVIAL_MAX_LINES = 5


def _is_frontend_file(f: FileDiff) -> bool:
    return f.language in _FRONTEND_LANGS or f.path.endswith((".vue", ".svelte"))


def _is_infra_file(f: FileDiff) -> bool:
    base = f.path.rsplit("/", 1)[-1]
    return (
        f.language in _INFRA_LANGS
        or ".github/workflows" in f.path
        or base == "Dockerfile"
        or base.startswith("Dockerfile")
    )


def _is_docs_file(f: FileDiff) -> bool:
    return f.language in _DOCS_LANGS or f.path.endswith((".md", ".rst", ".txt"))


def _is_code_file(f: FileDiff) -> bool:
    return f.language in _BACKEND_LANGS and not _is_docs_file(f)


@dataclass
class DiffClassification:
    languages: set[str]
    total_added: int
    is_frontend: bool
    is_backend: bool
    is_infra: bool
    only_docs: bool
    only_lockfiles: bool


@dataclass
class RoutingDecision:
    selected: list[str]
    reasons: dict[str, str]
    is_trivial: bool
    auto_approve_eligible: bool
    classification: DiffClassification = field(default=None)  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "reasons": self.reasons,
            "is_trivial": self.is_trivial,
            "auto_approve_eligible": self.auto_approve_eligible,
            "classification": {
                "languages": sorted(self.classification.languages),
                "total_added": self.classification.total_added,
                "is_frontend": self.classification.is_frontend,
                "is_backend": self.classification.is_backend,
                "is_infra": self.classification.is_infra,
                "only_docs": self.classification.only_docs,
            },
        }


def _classify(diff: NormalizedDiff) -> DiffClassification:
    files = diff.files
    only_docs = bool(files) and all(_is_docs_file(f) for f in files)
    only_lockfiles = bool(files) and all(f.path.rsplit("/", 1)[-1] in _LOCKFILES for f in files)
    return DiffClassification(
        languages=diff.languages,
        total_added=diff.total_added,
        is_frontend=any(_is_frontend_file(f) for f in files),
        is_backend=any(_is_code_file(f) for f in files),
        is_infra=any(_is_infra_file(f) for f in files),
        only_docs=only_docs,
        only_lockfiles=only_lockfiles,
    )


def triage(pr: PRMeta, diff: NormalizedDiff) -> RoutingDecision:
    """Select the minimal agent set for this diff and decide auto-approve eligibility."""
    c = _classify(diff)
    selected: list[str] = []
    reasons: dict[str, str] = {}

    def add(name: str, why: str) -> None:
        if name not in selected:
            selected.append(name)
            reasons[name] = why

    # Security always runs — it's cheap, high-value, and safe to run on anything.
    add("security", "always runs to catch secrets/vulnerabilities")

    if c.only_docs:
        add("documentation", "documentation-only change")
    else:
        add("ai_reviewer", "correctness review of intent vs. implementation")
        add("architecture", "source changed — structural review")
        add("documentation", "source changed — doc coverage")
        add("testing", "source changed — test coverage")
        if c.is_backend:
            add("performance", "backend/query code present")

    if c.is_frontend:
        add("accessibility", "frontend markup present")
    if c.is_infra:
        add("devops", "Docker/IaC/CI files present")

    is_trivial = (
        c.only_docs or c.only_lockfiles or (c.total_added <= _TRIVIAL_MAX_LINES and not c.is_infra)
    )
    # Auto-approve is only *eligible* for the safest classes; a clean review is still
    # required before it actually approves (decided in the orchestrator).
    auto_approve_eligible = c.only_docs or c.only_lockfiles

    decision = RoutingDecision(
        selected=selected,
        reasons=reasons,
        is_trivial=is_trivial,
        auto_approve_eligible=auto_approve_eligible,
    )
    decision.classification = c
    return decision
