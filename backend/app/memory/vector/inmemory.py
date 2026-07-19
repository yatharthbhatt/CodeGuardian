"""In-memory VectorStore (offline/tests).

Tenant isolation is structural: vectors live under ``self._data[tenant_id][collection]``,
so a search for one tenant cannot surface another tenant's vectors. Similarity is cosine
over the embedder's normalized vectors.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.memory.vector.base import Collection, Embedder, SearchHit, VectorRecord
from app.memory.vector.embedding import cosine


@dataclass
class _Stored:
    record: VectorRecord
    vector: list[float] = field(default_factory=list)


class InMemoryVectorStore:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        # tenant -> collection -> id -> stored
        self._data: dict[str, dict[str, dict[str, _Stored]]] = defaultdict(
            lambda: defaultdict(dict)
        )

    def upsert(self, tenant_id: str, collection: Collection, records: list[VectorRecord]) -> None:
        bucket = self._data[tenant_id][collection.value]
        for rec in records:
            bucket[rec.id] = _Stored(record=rec, vector=self._embedder.embed(rec.text))

    def search(
        self, tenant_id: str, collection: Collection, query: str, top_k: int = 5
    ) -> list[SearchHit]:
        q = self._embedder.embed(query)
        bucket = self._data.get(tenant_id, {}).get(collection.value, {})
        scored = [
            SearchHit(
                id=s.record.id,
                score=cosine(q, s.vector),
                text=s.record.text,
                payload=s.record.payload,
            )
            for s in bucket.values()
        ]
        scored = [h for h in scored if h.score > 0.0]
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]
