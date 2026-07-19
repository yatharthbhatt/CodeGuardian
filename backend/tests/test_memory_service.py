"""RepositoryMemory service: ingest → context, and that memory improves over time."""

from __future__ import annotations

from app.domain.findings import Dimension, Explanation, Finding, FindingSource, Severity
from app.memory.extract import extract_file_facts
from app.memory.graph.inmemory import InMemoryGraphStore
from app.memory.service import RepositoryMemory

from tests.conftest import diff_from_added, make_pr_n


def _mem() -> RepositoryMemory:
    return RepositoryMemory(InMemoryGraphStore())


def _finding(title: str, category: str, file_path: str) -> Finding:
    return Finding(
        agent="security",
        dimension=Dimension.SECURITY,
        category=category,
        severity=Severity.HIGH,
        confidence=0.9,
        title=title,
        message=f"{title} detail",
        file_path=file_path,
        line=1,
        source=FindingSource.DETERMINISTIC,
        explanation=Explanation(why="w", impact="i"),
    )


# --- extraction -----------------------------------------------------------
def test_extract_python_symbols_and_imports() -> None:
    diff = diff_from_added("app/a.py", ["from app.b import x", "def handler():", "class Thing:"])
    facts = extract_file_facts(diff.files[0])
    assert "handler" in facts.symbols
    assert "Thing" in facts.symbols
    assert "app/b.py" in facts.depends_on


# --- graph-backed context -------------------------------------------------
def test_blast_radius_surfaces_after_ingest() -> None:
    m = _mem()
    m.ingest_pr(make_pr_n(1), diff_from_added("app/a.py", ["from app.b import x"]), [])
    m.ingest_pr(make_pr_n(2), diff_from_added("app/b.py", ["def x():", "    return 1"]), [])
    ctx = m.context_for(make_pr_n(3), diff_from_added("app/b.py", ["def x():", "    return 2"]))
    assert "app/a.py" in ctx.blast_radius


def test_regression_risk_accrues_after_a_fix_pr() -> None:
    m = _mem()
    m.ingest_pr(
        make_pr_n(1, title="Add auth"), diff_from_added("app/auth.py", ["def login(): ..."]), []
    )
    before = m.context_for(make_pr_n(2), diff_from_added("app/auth.py", ["def login(): ..."]))
    assert before.regression == []

    m.ingest_pr(
        make_pr_n(3, title="Fix login bug"),
        diff_from_added("app/auth.py", ["def login(): ..."]),
        [],
    )
    after = m.context_for(make_pr_n(4), diff_from_added("app/auth.py", ["def login(): ..."]))
    assert any(r.file_path == "app/auth.py" and r.past_bug_count == 1 for r in after.regression)


# --- RAG ------------------------------------------------------------------
def test_rag_surfaces_similar_past_finding() -> None:
    m = _mem()
    # A past finding describes an unsafe cursor.execute SELECT query (its text shares
    # vocabulary with the new diff — how lexical RAG retrieval actually works).
    m.ingest_pr(
        make_pr_n(1, title="Add query"),
        diff_from_added("app/db.py", ["cursor.execute('SELECT * FROM t')"]),
        [_finding("SQL injection in cursor.execute SELECT query", "sql-injection", "app/db.py")],
    )
    ctx = m.context_for(
        make_pr_n(2, title="Change query"),
        diff_from_added("app/other.py", ["cursor.execute(f'SELECT * FROM t WHERE id={x}')"]),
    )
    assert any("SQL injection" in s.title for s in ctx.similar_past_findings)


# --- insights -------------------------------------------------------------
def test_insights_emit_blast_and_regression_findings() -> None:
    m = _mem()
    m.ingest_pr(make_pr_n(1), diff_from_added("app/a.py", ["from app.b import x"]), [])
    m.ingest_pr(
        make_pr_n(2, title="Fix bug in b"), diff_from_added("app/b.py", ["def x(): ..."]), []
    )
    ctx = m.context_for(make_pr_n(3), diff_from_added("app/b.py", ["def x(): return 1"]))
    cats = {f.category for f in m.insights(ctx)}
    assert "blast-radius" in cats
    assert "regression-risk" in cats


def test_service_is_tenant_isolated() -> None:
    m = _mem()
    m.ingest_pr(make_pr_n(1, tenant="A"), diff_from_added("app/a.py", ["from app.b import x"]), [])
    # Same repo name, different tenant → no shared memory.
    ctx = m.context_for(make_pr_n(2, tenant="B"), diff_from_added("app/b.py", ["def x(): ..."]))
    assert ctx.blast_radius == []
    assert ctx.is_empty()
