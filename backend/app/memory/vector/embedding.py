"""Deterministic, offline embedder (no model, no network).

A hashing bag-of-words embedder: tokens are hashed into a fixed-dimension vector, then
L2-normalized. It captures lexical overlap well enough for RAG demos and makes tests
deterministic and dependency-free. A real embedder (OpenAI/Voyage/local) implements the
same :class:`app.memory.vector.base.Embedder` interface and is swapped in for production.
"""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            h = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0  # signed hashing reduces collisions
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
