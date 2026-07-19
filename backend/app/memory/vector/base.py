"""Vector store + embedder abstractions (PRD §11).

Collections: ``symbols``, ``past_findings``, ``pr_discussions``, ``docs``. Retrieval feeds
RAG context to agents. Both implementations (in-memory + Qdrant) are **tenant-scoped**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Collection(StrEnum):
    SYMBOLS = "symbols"
    PAST_FINDINGS = "past_findings"
    PR_DISCUSSIONS = "pr_discussions"
    DOCS = "docs"


@dataclass
class VectorRecord:
    id: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    id: str
    score: float
    text: str
    payload: dict[str, Any]


class Embedder(Protocol):
    """Turns text into a fixed-dimension vector."""

    dim: int

    def embed(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    """Tenant-scoped similarity store."""

    def upsert(
        self, tenant_id: str, collection: Collection, records: list[VectorRecord]
    ) -> None: ...

    def search(
        self, tenant_id: str, collection: Collection, query: str, top_k: int = 5
    ) -> list[SearchHit]: ...
