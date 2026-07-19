"""Knowledge-graph algorithms + tenant isolation (PRD §11, §9.2)."""

from __future__ import annotations

from app.memory.graph.base import FileNode
from app.memory.graph.inmemory import InMemoryGraphStore


def _seed(g: InMemoryGraphStore, tenant: str = "t", repo: str = "r") -> None:
    g.upsert_files(
        tenant,
        repo,
        [
            FileNode("a.py", "", (), ("b.py",)),  # a depends on b
            FileNode("c.py", "", (), ("a.py",)),  # c depends on a
            FileNode("b.py", "", (), ()),
        ],
    )


def test_blast_radius_is_reverse_reachability() -> None:
    g = InMemoryGraphStore()
    _seed(g)
    assert g.blast_radius("t", "r", ["b.py"]) == ["a.py", "c.py"]
    assert g.blast_radius("t", "r", ["a.py"]) == ["c.py"]
    assert g.blast_radius("t", "r", ["c.py"]) == []


def test_cycle_detection() -> None:
    g = InMemoryGraphStore()
    g.upsert_files(
        "t", "r", [FileNode("x.py", "", (), ("y.py",)), FileNode("y.py", "", (), ("x.py",))]
    )
    assert g.find_cycles("t", "r") == [["x.py", "y.py"]]


def test_no_false_cycle_on_dag() -> None:
    g = InMemoryGraphStore()
    _seed(g)
    assert g.find_cycles("t", "r") == []


def test_regression_history_accumulates() -> None:
    g = InMemoryGraphStore()
    g.record_bug("t", "r", "f.py", 10)
    g.record_bug("t", "r", "f.py", 20)
    info = g.regression_risk("t", "r", "f.py")
    assert info.past_bug_count == 2
    assert info.last_bug_pr == 20


def test_upsert_replaces_stale_dependencies() -> None:
    g = InMemoryGraphStore()
    g.upsert_files("t", "r", [FileNode("a.py", "", (), ("b.py",))])
    assert g.blast_radius("t", "r", ["b.py"]) == ["a.py"]
    # a.py now depends on c.py instead of b.py.
    g.upsert_files("t", "r", [FileNode("a.py", "", (), ("c.py",))])
    assert g.blast_radius("t", "r", ["b.py"]) == []
    assert g.blast_radius("t", "r", ["c.py"]) == ["a.py"]


def test_tenant_isolation_by_construction() -> None:
    g = InMemoryGraphStore()
    _seed(g, tenant="A")
    g.record_bug("A", "r", "a.py", 1)
    # Tenant B cannot see tenant A's graph or history.
    assert g.blast_radius("B", "r", ["b.py"]) == []
    assert g.regression_risk("B", "r", "a.py").past_bug_count == 0
    assert g.find_cycles("B", "r") == []
