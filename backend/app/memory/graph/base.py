"""Repository knowledge-graph store (PRD §11).

Models Repo → Module → File → Symbol with CALLS and DEPENDS_ON edges, PR → TOUCHED
history, and Bug history. Two implementations share this protocol: an in-memory reference
(offline/tests) and a Neo4j adapter (production). **Every method is tenant-scoped** — a
tenant id is required on every call and isolation is enforced by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class FileNode:
    path: str
    module: str
    symbols: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()  # repo-relative paths this file imports


@dataclass
class RegressionInfo:
    file_path: str
    past_bug_count: int
    last_bug_pr: int | None


class GraphStore(Protocol):
    """Tenant-scoped repository knowledge graph."""

    def upsert_files(self, tenant_id: str, repo: str, files: list[FileNode]) -> None:
        """Create/update file+module+symbol nodes and DEPENDS_ON edges."""
        ...

    def record_pr_touch(self, tenant_id: str, repo: str, pr_number: int, paths: list[str]) -> None:
        """Record that a PR touched these files (PR → TOUCHED)."""
        ...

    def record_bug(self, tenant_id: str, repo: str, path: str, pr_number: int) -> None:
        """Record that a bug was associated with a file (Bug history)."""
        ...

    def blast_radius(self, tenant_id: str, repo: str, paths: list[str]) -> list[str]:
        """Files that (transitively) depend on any of ``paths`` — the change's blast radius."""
        ...

    def regression_risk(self, tenant_id: str, repo: str, path: str) -> RegressionInfo:
        """Historical bug count for a file (higher = riskier to touch)."""
        ...

    def find_cycles(self, tenant_id: str, repo: str) -> list[list[str]]:
        """Circular dependencies (DEPENDS_ON SCCs of size > 1, or self-loops)."""
        ...


@dataclass
class _RepoGraph:
    """Per-(tenant, repo) adjacency + history. Not shared across tenants."""

    depends_on: dict[str, set[str]] = field(default_factory=dict)  # file -> imported files
    dependents: dict[str, set[str]] = field(default_factory=dict)  # reverse edges
    symbols: dict[str, set[str]] = field(default_factory=dict)
    modules: dict[str, str] = field(default_factory=dict)  # file -> module
    touched_by: dict[str, set[int]] = field(default_factory=dict)  # file -> pr numbers
    bug_count: dict[str, int] = field(default_factory=dict)
    last_bug_pr: dict[str, int] = field(default_factory=dict)
