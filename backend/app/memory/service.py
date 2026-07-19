"""RepositoryMemory — the long-term memory service (PRD §11).

Combines the knowledge graph + vector store + embedder. On every PR it:
  * updates the graph incrementally (files/symbols/DEPENDS_ON, PR→TOUCHED, Bug history),
  * indexes findings/symbols/discussions for RAG,
and before a review it produces a :class:`MemoryContext` (blast radius, regression risk,
dependency cycles, similar past findings) plus derived informational findings.

All operations are tenant-scoped (keyed on ``pr.tenant_id``).
"""

from __future__ import annotations

import re

from app.domain.findings import (
    Dimension,
    Explanation,
    Finding,
    FindingSource,
    Severity,
)
from app.memory.extract import FileFacts, extract_file_facts
from app.memory.graph.base import FileNode, GraphStore
from app.memory.types import MemoryContext, SimilarFinding
from app.memory.vector.base import Collection, Embedder, VectorRecord, VectorStore
from app.memory.vector.embedding import HashingEmbedder
from app.memory.vector.inmemory import InMemoryVectorStore
from app.review.diff import NormalizedDiff
from app.review.state import PRMeta

_FIX_HINT = re.compile(r"\b(fix(e[ds])?|bug|hotfix|patch|regression|resolve[sd]?|closes)\b", re.I)


class RepositoryMemory:
    def __init__(
        self,
        graph: GraphStore,
        vector: VectorStore | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._graph = graph
        self._embedder = embedder or HashingEmbedder()
        self._vector = vector or InMemoryVectorStore(self._embedder)

    # --- write path --------------------------------------------------------
    def update_structure(self, pr: PRMeta, diff: NormalizedDiff) -> list[FileFacts]:
        """Incrementally add this PR's files/symbols/DEPENDS_ON edges to the graph.

        Called BEFORE the review so blast-radius and cycle detection reflect the current
        change. Returns the extracted facts so ``record_outcome`` can reuse them.
        """
        facts = [extract_file_facts(f) for f in diff.files]
        self._graph.upsert_files(
            pr.tenant_id,
            pr.repo_full_name,
            [FileNode(f.path, f.module, tuple(f.symbols), tuple(f.depends_on)) for f in facts],
        )
        return facts

    def record_outcome(
        self,
        pr: PRMeta,
        diff: NormalizedDiff,
        findings: list[Finding],
        facts: list[FileFacts] | None = None,
    ) -> None:
        """Record PR→TOUCHED, bug history, and RAG index — called AFTER the review."""
        tenant, repo = pr.tenant_id, pr.repo_full_name
        if facts is None:
            facts = [extract_file_facts(f) for f in diff.files]
        paths = [f.path for f in diff.files]
        self._graph.record_pr_touch(tenant, repo, pr.number, paths)

        # A fix-shaped PR marks its touched files as historically buggy (regression signal).
        if _FIX_HINT.search(f"{pr.title}\n{pr.body}"):
            for p in paths:
                self._graph.record_bug(tenant, repo, p, pr.number)

        self._index_for_rag(pr, facts, findings)

    def ingest_pr(self, pr: PRMeta, diff: NormalizedDiff, findings: list[Finding]) -> None:
        """Convenience: update structure + record outcome in one call."""
        facts = self.update_structure(pr, diff)
        self.record_outcome(pr, diff, findings, facts)

    def _index_for_rag(self, pr: PRMeta, facts: list[FileFacts], findings: list[Finding]) -> None:
        tenant = pr.tenant_id
        if findings:
            self._vector.upsert(
                tenant,
                Collection.PAST_FINDINGS,
                [
                    VectorRecord(
                        id=f"{pr.number}:{i}",
                        text=f"{fnd.title}. {fnd.message}",
                        payload={
                            "title": fnd.title,
                            "category": fnd.category,
                            "file_path": fnd.file_path,
                        },
                    )
                    for i, fnd in enumerate(findings)
                ],
            )
        symbols = [
            VectorRecord(id=f"{f.path}:{s}", text=f"{s} in {f.path}", payload={"file_path": f.path})
            for f in facts
            for s in f.symbols
        ]
        if symbols:
            self._vector.upsert(tenant, Collection.SYMBOLS, symbols)
        self._vector.upsert(
            tenant,
            Collection.PR_DISCUSSIONS,
            [VectorRecord(id=str(pr.number), text=f"{pr.title}. {pr.body}", payload={})],
        )

    # --- read path ---------------------------------------------------------
    def context_for(self, pr: PRMeta, diff: NormalizedDiff) -> MemoryContext:
        tenant, repo = pr.tenant_id, pr.repo_full_name
        touched = [f.path for f in diff.files]

        blast = self._graph.blast_radius(tenant, repo, touched)
        regression = [
            info
            for p in touched
            if (info := self._graph.regression_risk(tenant, repo, p)).past_bug_count > 0
        ]
        touched_set = set(touched)
        cycles = [c for c in self._graph.find_cycles(tenant, repo) if touched_set.intersection(c)]

        query = pr.title + "\n" + "\n".join(f.added_text for f in diff.files)[:4000]
        hits = self._vector.search(tenant, Collection.PAST_FINDINGS, query, top_k=5)
        similar = [
            SimilarFinding(
                title=str(h.payload.get("title", h.text[:80])),
                category=str(h.payload.get("category", "")),
                score=h.score,
                file_path=h.payload.get("file_path"),
            )
            for h in hits
        ]
        return MemoryContext(
            blast_radius=blast,
            regression=regression,
            cycles=cycles,
            similar_past_findings=similar,
        )

    # --- derived findings --------------------------------------------------
    def insights(self, context: MemoryContext) -> list[Finding]:
        """Turn memory into surfaced findings (blast radius + regression risk)."""
        out: list[Finding] = []
        if context.blast_radius:
            preview = ", ".join(context.blast_radius[:8])
            out.append(
                Finding(
                    agent="memory",
                    dimension=Dimension.ARCHITECTURE,
                    category="blast-radius",
                    severity=Severity.INFO,
                    confidence=0.9,
                    title=f"Change impacts {len(context.blast_radius)} downstream file(s)",
                    message=f"Files that depend on this change: {preview}.",
                    file_path=None,
                    source=FindingSource.DETERMINISTIC,
                    explanation=Explanation(
                        why="Edits to widely-depended-on files ripple across the codebase.",
                        impact="Downstream modules may need re-testing.",
                        alternative="Review the listed dependents and their tests.",
                        complexity="low",
                    ),
                )
            )
        for info in context.regression:
            sev = Severity.MEDIUM if info.past_bug_count >= 3 else Severity.LOW
            out.append(
                Finding(
                    agent="memory",
                    dimension=Dimension.CORRECTNESS,
                    category="regression-risk",
                    severity=sev,
                    confidence=min(0.5 + 0.1 * info.past_bug_count, 0.9),
                    title=f"Regression-prone file ({info.past_bug_count} past bug fixes)",
                    message=(
                        f"{info.file_path} has {info.past_bug_count} prior bug fix(es) "
                        f"(last in PR #{info.last_bug_pr}). Review with extra care."
                    ),
                    file_path=info.file_path,
                    source=FindingSource.DETERMINISTIC,
                    explanation=Explanation(
                        why="Files with a history of bugs are more likely to regress.",
                        impact="Higher chance of reintroducing a defect.",
                        alternative="Add targeted tests around previously-broken behavior.",
                        complexity="medium",
                    ),
                )
            )
        return out
