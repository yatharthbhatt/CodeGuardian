"""Vector store + embedder: relevance, determinism, tenant isolation (PRD §11, §9.2)."""

from __future__ import annotations

import math

from app.memory.vector.base import Collection, VectorRecord
from app.memory.vector.embedding import HashingEmbedder, cosine
from app.memory.vector.inmemory import InMemoryVectorStore


def test_embedder_is_deterministic_and_normalized() -> None:
    e = HashingEmbedder(dim=128)
    v1 = e.embed("sql injection in login handler")
    v2 = e.embed("sql injection in login handler")
    assert v1 == v2
    assert abs(math.sqrt(sum(x * x for x in v1)) - 1.0) < 1e-9


def test_cosine_similarity_of_related_text_is_higher() -> None:
    e = HashingEmbedder()
    a = e.embed("sql injection vulnerability in query")
    related = e.embed("possible sql injection in the query")
    unrelated = e.embed("missing alt text on an image element")
    assert cosine(a, related) > cosine(a, unrelated)


def test_search_ranks_relevant_record_first() -> None:
    store = InMemoryVectorStore(HashingEmbedder())
    store.upsert(
        "t",
        Collection.PAST_FINDINGS,
        [
            VectorRecord("1", "SQL injection via string interpolation", {"title": "SQL injection"}),
            VectorRecord("2", "Missing alt text on image", {"title": "a11y"}),
        ],
    )
    hits = store.search("t", Collection.PAST_FINDINGS, "possible sql injection in query", top_k=2)
    assert hits
    assert hits[0].payload["title"] == "SQL injection"


def test_vector_tenant_isolation() -> None:
    store = InMemoryVectorStore(HashingEmbedder())
    store.upsert("A", Collection.SYMBOLS, [VectorRecord("1", "login function", {})])
    # Tenant B's search cannot surface tenant A's vectors.
    assert store.search("B", Collection.SYMBOLS, "login", top_k=5) == []
    assert store.search("A", Collection.SYMBOLS, "login", top_k=5)
