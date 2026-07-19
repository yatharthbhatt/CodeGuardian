"""In-memory reference GraphStore (offline/tests).

Tenant isolation is structural: all state lives under ``self._tenants[tenant_id]``, so a
query for one tenant can never read another tenant's graph. Implements blast-radius
(reverse-dependency BFS), cycle detection (Tarjan SCC), and regression history.
"""

from __future__ import annotations

from collections import defaultdict, deque

from app.memory.graph.base import FileNode, RegressionInfo, _RepoGraph


class InMemoryGraphStore:
    def __init__(self) -> None:
        # tenant_id -> repo -> graph
        self._tenants: dict[str, dict[str, _RepoGraph]] = defaultdict(
            lambda: defaultdict(_RepoGraph)
        )

    def _graph(self, tenant_id: str, repo: str) -> _RepoGraph:
        return self._tenants[tenant_id][repo]

    def upsert_files(self, tenant_id: str, repo: str, files: list[FileNode]) -> None:
        g = self._graph(tenant_id, repo)
        for f in files:
            g.modules[f.path] = f.module
            g.symbols[f.path] = set(f.symbols)
            # Reset this file's outgoing deps to the current snapshot, then rebuild reverse.
            old = g.depends_on.get(f.path, set())
            for dep in old:
                g.dependents.get(dep, set()).discard(f.path)
            g.depends_on[f.path] = set(f.depends_on)
            for dep in f.depends_on:
                g.dependents.setdefault(dep, set()).add(f.path)

    def record_pr_touch(self, tenant_id: str, repo: str, pr_number: int, paths: list[str]) -> None:
        g = self._graph(tenant_id, repo)
        for p in paths:
            g.touched_by.setdefault(p, set()).add(pr_number)

    def graph_export(self, tenant_id: str, repo: str) -> dict[str, list[dict[str, object]]]:
        """Nodes + DEPENDS_ON edges for the dashboard knowledge-graph view (tenant-scoped)."""
        g = self._graph(tenant_id, repo)
        files = set(g.modules) | set(g.depends_on) | set(g.dependents)
        nodes: list[dict[str, object]] = [
            {"id": path, "module": g.modules.get(path, "."), "bugs": g.bug_count.get(path, 0)}
            for path in sorted(files)
        ]
        edges: list[dict[str, object]] = [
            {"source": src, "target": dst}
            for src, deps in sorted(g.depends_on.items())
            for dst in sorted(deps)
        ]
        return {"nodes": nodes, "edges": edges}

    def record_bug(self, tenant_id: str, repo: str, path: str, pr_number: int) -> None:
        g = self._graph(tenant_id, repo)
        g.bug_count[path] = g.bug_count.get(path, 0) + 1
        g.last_bug_pr[path] = pr_number

    def blast_radius(self, tenant_id: str, repo: str, paths: list[str]) -> list[str]:
        g = self._graph(tenant_id, repo)
        seen: set[str] = set()
        queue: deque[str] = deque(paths)
        start = set(paths)
        while queue:
            node = queue.popleft()
            for dependent in g.dependents.get(node, set()):
                if dependent not in seen:
                    seen.add(dependent)
                    queue.append(dependent)
        return sorted(seen - start)

    def regression_risk(self, tenant_id: str, repo: str, path: str) -> RegressionInfo:
        g = self._graph(tenant_id, repo)
        return RegressionInfo(
            file_path=path,
            past_bug_count=g.bug_count.get(path, 0),
            last_bug_pr=g.last_bug_pr.get(path),
        )

    def find_cycles(self, tenant_id: str, repo: str) -> list[list[str]]:
        """Return strongly-connected components with a real cycle (Tarjan)."""
        g = self._graph(tenant_id, repo)
        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        low: dict[str, int] = {}
        result: list[list[str]] = []

        def strongconnect(v: str) -> None:
            indices[v] = low[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            for w in g.depends_on.get(v, set()):
                if w not in indices:
                    strongconnect(w)
                    low[v] = min(low[v], low[w])
                elif w in on_stack:
                    low[v] = min(low[v], indices[w])
            if low[v] == indices[v]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == v:
                        break
                if len(component) > 1 or (v in g.depends_on.get(v, set())):
                    result.append(sorted(component))

        for node in list(g.depends_on):
            if node not in indices:
                strongconnect(node)
        return result
