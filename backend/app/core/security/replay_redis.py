"""Redis-backed replay guard (production).

Implements the :class:`app.core.security.webhook.ReplayGuard` protocol using an atomic
``SET key val NX EX`` so replay protection works across worker processes (the in-memory
guard only covers a single process). Keyed on GitHub's per-delivery id.
"""

from __future__ import annotations

from app.core.security.webhook import ReplayError


class RedisReplayGuard:
    def __init__(self, redis_url: str, window_seconds: int = 300, prefix: str = "cg:wh:") -> None:
        import redis  # imported lazily so redis is only needed where this is used

        self._client = redis.Redis.from_url(redis_url)
        self._window = window_seconds
        self._prefix = prefix

    def check_and_remember(self, delivery_id: str) -> None:
        if not delivery_id:
            raise ReplayError("Missing delivery id.")
        # NX = only set if absent; EX = auto-expire. Returns True on first sighting.
        first_time = self._client.set(f"{self._prefix}{delivery_id}", "1", nx=True, ex=self._window)
        if not first_time:
            raise ReplayError(f"Duplicate delivery id: {delivery_id}")
