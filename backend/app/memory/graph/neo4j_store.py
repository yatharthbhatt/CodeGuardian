"""Neo4j GraphStore adapter (production, PRD §11).

Every node carries a ``tenant`` property and every query filters on it, so tenant
isolation holds at the database. Network-backed; exercised in integration environments,
not the offline unit suite (which uses ``InMemoryGraphStore``).
"""

from __future__ import annotations

from app.memory.graph.base import FileNode, RegressionInfo


class Neo4jGraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase  # lazy: neo4j is an optional dependency

        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def upsert_files(self, tenant_id: str, repo: str, files: list[FileNode]) -> None:
        cypher = """
        MERGE (r:Repo {tenant:$tenant, name:$repo})
        WITH r
        UNWIND $files AS f
          MERGE (m:Module {tenant:$tenant, repo:$repo, name:f.module})
          MERGE (r)-[:HAS]->(m)
          MERGE (file:File {tenant:$tenant, repo:$repo, path:f.path})
          MERGE (m)-[:CONTAINS]->(file)
          WITH file, f
          // Reset outgoing DEPENDS_ON to the current snapshot.
          OPTIONAL MATCH (file)-[old:DEPENDS_ON]->()
          DELETE old
          WITH file, f
          UNWIND (CASE WHEN size(f.depends_on)=0 THEN [null] ELSE f.depends_on END) AS dep
            FOREACH (_ IN CASE WHEN dep IS NULL THEN [] ELSE [1] END |
              MERGE (d:File {tenant:$tenant, repo:$repo, path:dep})
              MERGE (file)-[:DEPENDS_ON]->(d))
          WITH file, f
          UNWIND (CASE WHEN size(f.symbols)=0 THEN [null] ELSE f.symbols END) AS sym
            FOREACH (_ IN CASE WHEN sym IS NULL THEN [] ELSE [1] END |
              MERGE (s:Symbol {tenant:$tenant, repo:$repo, name:sym, file:f.path})
              MERGE (file)-[:DEFINES]->(s))
        """
        payload = [
            {
                "path": f.path,
                "module": f.module,
                "symbols": list(f.symbols),
                "depends_on": list(f.depends_on),
            }
            for f in files
        ]
        with self._driver.session() as s:
            s.run(cypher, tenant=tenant_id, repo=repo, files=payload)

    def record_pr_touch(self, tenant_id: str, repo: str, pr_number: int, paths: list[str]) -> None:
        cypher = """
        MERGE (pr:PR {tenant:$tenant, repo:$repo, number:$number})
        WITH pr
        UNWIND $paths AS p
          MERGE (f:File {tenant:$tenant, repo:$repo, path:p})
          MERGE (pr)-[:TOUCHED]->(f)
        """
        with self._driver.session() as s:
            s.run(cypher, tenant=tenant_id, repo=repo, number=pr_number, paths=paths)

    def record_bug(self, tenant_id: str, repo: str, path: str, pr_number: int) -> None:
        cypher = """
        MERGE (f:File {tenant:$tenant, repo:$repo, path:$path})
        MERGE (pr:PR {tenant:$tenant, repo:$repo, number:$number})
        CREATE (b:Bug {tenant:$tenant, repo:$repo})
        MERGE (b)-[:IN_FILE]->(f)
        MERGE (b)-[:FIXED_IN]->(pr)
        """
        with self._driver.session() as s:
            s.run(cypher, tenant=tenant_id, repo=repo, path=path, number=pr_number)

    def blast_radius(self, tenant_id: str, repo: str, paths: list[str]) -> list[str]:
        cypher = """
        UNWIND $paths AS p
        MATCH (start:File {tenant:$tenant, repo:$repo, path:p})
        MATCH (dependent:File)-[:DEPENDS_ON*1..]->(start)
        WHERE dependent.tenant=$tenant AND dependent.repo=$repo
              AND NOT dependent.path IN $paths
        RETURN DISTINCT dependent.path AS path ORDER BY path
        """
        with self._driver.session() as s:
            return [r["path"] for r in s.run(cypher, tenant=tenant_id, repo=repo, paths=paths)]

    def regression_risk(self, tenant_id: str, repo: str, path: str) -> RegressionInfo:
        cypher = """
        MATCH (f:File {tenant:$tenant, repo:$repo, path:$path})
        OPTIONAL MATCH (b:Bug)-[:IN_FILE]->(f)
        OPTIONAL MATCH (b)-[:FIXED_IN]->(pr:PR)
        RETURN count(b) AS bugs, max(pr.number) AS last_pr
        """
        with self._driver.session() as s:
            rec = s.run(cypher, tenant=tenant_id, repo=repo, path=path).single()
        bugs = int(rec["bugs"]) if rec else 0
        last = int(rec["last_pr"]) if rec and rec["last_pr"] is not None else None
        return RegressionInfo(file_path=path, past_bug_count=bugs, last_bug_pr=last)

    def find_cycles(self, tenant_id: str, repo: str) -> list[list[str]]:
        # Detect 2- and 3-node cycles via path queries (cheap, covers common cases).
        cypher = """
        MATCH (a:File {tenant:$tenant, repo:$repo})-[:DEPENDS_ON]->(b:File)-[:DEPENDS_ON*0..2]->(a)
        WHERE a.path < b.path
        RETURN DISTINCT a.path AS a, b.path AS b
        """
        cycles: list[list[str]] = []
        with self._driver.session() as s:
            for r in s.run(cypher, tenant=tenant_id, repo=repo):
                cycles.append(sorted([r["a"], r["b"]]))
        return cycles
