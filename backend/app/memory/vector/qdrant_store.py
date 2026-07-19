"""Qdrant VectorStore adapter (production, PRD §11).

One Qdrant collection per logical collection; tenant isolation is enforced with a payload
filter (``tenant`` must match) on every search, plus a payload index on ``tenant`` for
speed. Network-backed; not exercised in the offline unit suite.
"""

from __future__ import annotations

from app.memory.vector.base import Collection, Embedder, SearchHit, VectorRecord


class QdrantVectorStore:
    def __init__(self, url: str, embedder: Embedder, prefix: str = "cg_") -> None:
        from qdrant_client import QdrantClient  # lazy: optional dependency

        self._client = QdrantClient(url=url)
        self._embedder = embedder
        self._prefix = prefix

    def _collection(self, collection: Collection) -> str:
        return f"{self._prefix}{collection.value}"

    def ensure_collections(self) -> None:
        from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

        for coll in Collection:
            name = self._collection(coll)
            if not self._client.collection_exists(name):
                self._client.create_collection(
                    name,
                    vectors_config=VectorParams(size=self._embedder.dim, distance=Distance.COSINE),
                )
                # Index tenant for fast, isolated filtering.
                self._client.create_payload_index(
                    name, field_name="tenant", field_schema=PayloadSchemaType.KEYWORD
                )

    def upsert(self, tenant_id: str, collection: Collection, records: list[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=rec.id,
                vector=self._embedder.embed(rec.text),
                payload={"tenant": tenant_id, "text": rec.text, **rec.payload},
            )
            for rec in records
        ]
        self._client.upsert(self._collection(collection), points=points)

    def search(
        self, tenant_id: str, collection: Collection, query: str, top_k: int = 5
    ) -> list[SearchHit]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        tenant_filter = Filter(
            must=[FieldCondition(key="tenant", match=MatchValue(value=tenant_id))]
        )
        hits = self._client.search(
            self._collection(collection),
            query_vector=self._embedder.embed(query),
            query_filter=tenant_filter,  # tenant isolation enforced on every search
            limit=top_k,
        )
        return [
            SearchHit(
                id=str(h.id),
                score=float(h.score),
                text=str((h.payload or {}).get("text", "")),
                payload=dict(h.payload or {}),
            )
            for h in hits
        ]
