"""Token-bucket rate limiter for PR chat (PRD §9.5).

Bounds how often a given thread/user can trigger an LLM answer, protecting against abuse
and runaway cost. In-memory here (single process); a Redis token bucket is the multi-process
production backing (same interface).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Protocol


class RateLimiter(Protocol):
    def allow(self, key: str) -> bool: ...


@dataclass
class _Bucket:
    tokens: float
    updated: float


@dataclass
class InMemoryRateLimiter:
    capacity: int = 5
    refill_per_sec: float = 0.2  # 1 token / 5s → ~12 messages/min burst-capped at `capacity`
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                self._buckets[key] = _Bucket(tokens=self.capacity - 1, updated=now)
                return True
            # Refill based on elapsed time, capped at capacity.
            b.tokens = min(self.capacity, b.tokens + (now - b.updated) * self.refill_per_sec)
            b.updated = now
            if b.tokens >= 1:
                b.tokens -= 1
                return True
            return False
