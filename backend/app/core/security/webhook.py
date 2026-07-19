"""GitHub webhook authentication (PRD §9.1).

Threat → mitigation:
  * Forged/spoofed webhook          → HMAC-SHA256 signature verification.
  * Timing side-channel on compare  → ``hmac.compare_digest`` (constant-time).
  * Replay of a captured delivery    → per-delivery-id dedupe with a TTL window.
  * Oversized-body DoS               → caller enforces ``webhook_max_body_bytes`` first.

GitHub signs the *raw request body* with the shared secret and sends the result in
the ``X-Hub-Signature-256: sha256=<hex>`` header, plus a unique ``X-GitHub-Delivery``
id per delivery. We verify the signature over the exact bytes we received (never the
re-serialized JSON) and reject any delivery id we have already processed.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from typing import Final, Protocol

_SIG_PREFIX: Final[str] = "sha256="


class SignatureError(Exception):
    """Raised when a webhook signature is missing, malformed, or invalid."""


class ReplayError(Exception):
    """Raised when a webhook delivery id has already been seen (replay/duplicate)."""


def compute_signature(secret: str, body: bytes) -> str:
    """Return the ``sha256=<hex>`` signature GitHub would send for ``body``."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_SIG_PREFIX}{digest}"


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> None:
    """Verify a GitHub ``X-Hub-Signature-256`` header against ``body``.

    Raises :class:`SignatureError` on any problem. Uses a constant-time compare
    to avoid leaking how many leading bytes matched.
    """
    if not secret:
        # Fail closed: without a configured secret we cannot authenticate anything.
        raise SignatureError("Webhook secret is not configured.")
    if not signature_header or not signature_header.startswith(_SIG_PREFIX):
        raise SignatureError("Missing or malformed signature header.")

    expected = compute_signature(secret, body)
    # compare_digest over equal-length ASCII strings — constant time.
    if not hmac.compare_digest(expected, signature_header):
        raise SignatureError("Signature mismatch.")


class ReplayGuard(Protocol):
    """Pluggable replay/idempotency store.

    Phase 0 ships an in-memory implementation for single-process dev/tests; a
    Redis-backed implementation is wired in Phase 1 so the guard works across
    worker processes (SETNX with TTL).
    """

    def check_and_remember(self, delivery_id: str) -> None:
        """Record ``delivery_id``; raise :class:`ReplayError` if already seen."""
        ...


@dataclass
class InMemoryReplayGuard:
    """Thread-safe, TTL-bounded in-memory replay guard.

    Not durable across restarts and not shared across processes — good enough for
    local dev and unit tests. Production uses the Redis guard (Phase 1).
    """

    window_seconds: int = 300
    _seen: dict[str, float] = None  # type: ignore[assignment]
    _lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._seen = {}
        self._lock = threading.Lock()

    def check_and_remember(self, delivery_id: str) -> None:
        if not delivery_id:
            raise ReplayError("Missing delivery id.")
        now = time.monotonic()
        with self._lock:
            self._evict(now)
            if delivery_id in self._seen:
                raise ReplayError(f"Duplicate delivery id: {delivery_id}")
            self._seen[delivery_id] = now

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_seconds
        stale = [k for k, ts in self._seen.items() if ts < cutoff]
        for k in stale:
            del self._seen[k]
