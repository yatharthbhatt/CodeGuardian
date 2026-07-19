"""Immutable, hash-chained audit log (PRD §9.8).

Every state-changing action appends an event whose hash chains to the previous event:
``hash = sha256(prev_hash || payload_hash)``. Any insertion, deletion, reordering, or
mutation breaks the chain and is detected by :meth:`verify`. Tenant-scoped by construction.

In-memory here (offline/tests); production writes to the append-only, hash-chained
``audit_events`` table (PRD §10). The dashboard Audit Log view reads via ``list_events``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol

_GENESIS = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _payload_hash(tenant_id: str, actor: str, action: str, ts: str, detail: dict[str, Any]) -> str:
    body = _canonical(
        {"tenant": tenant_id, "actor": actor, "action": action, "ts": ts, "detail": detail}
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _chain_hash(prev_hash: str, payload_hash: str) -> str:
    return hashlib.sha256(f"{prev_hash}{payload_hash}".encode()).hexdigest()


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    tenant_id: str
    actor: str
    action: str
    ts: str
    detail: dict[str, Any]
    payload_hash: str
    prev_hash: str
    hash: str


class AuditStore(Protocol):
    def record(
        self, tenant_id: str, actor: str, action: str, detail: dict[str, Any] | None = None
    ) -> AuditEvent: ...

    def list_events(self, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]: ...

    def verify(self, tenant_id: str) -> bool: ...


class HashChainedAuditLog:
    def __init__(self) -> None:
        self._chains: dict[str, list[AuditEvent]] = defaultdict(list)

    def record(
        self, tenant_id: str, actor: str, action: str, detail: dict[str, Any] | None = None
    ) -> AuditEvent:
        chain = self._chains[tenant_id]
        prev_hash = chain[-1].hash if chain else _GENESIS
        ts = dt.datetime.now(dt.UTC).isoformat()
        detail = detail or {}
        ph = _payload_hash(tenant_id, actor, action, ts, detail)
        event = AuditEvent(
            seq=len(chain),
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            ts=ts,
            detail=detail,
            payload_hash=ph,
            prev_hash=prev_hash,
            hash=_chain_hash(prev_hash, ph),
        )
        chain.append(event)
        return event

    def list_events(self, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        events = self._chains.get(tenant_id, [])[-limit:]
        return [
            {
                "seq": e.seq,
                "actor": e.actor,
                "action": e.action,
                "ts": e.ts,
                "detail": e.detail,
                "hash": e.hash,
                "prev_hash": e.prev_hash,
            }
            for e in reversed(events)
        ]

    def verify(self, tenant_id: str) -> bool:
        """Recompute the whole chain; return False if anything was tampered with."""
        prev = _GENESIS
        for e in self._chains.get(tenant_id, []):
            ph = _payload_hash(e.tenant_id, e.actor, e.action, e.ts, e.detail)
            if ph != e.payload_hash or e.prev_hash != prev:
                return False
            if _chain_hash(e.prev_hash, ph) != e.hash:
                return False
            prev = e.hash
        return True
