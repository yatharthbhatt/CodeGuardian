"""Feedback store (PRD §8.12, §8.14 — Golden-Path learning).

Records what developers do with each finding (accept / reject / edit) so the platform can
learn each team's norms over time. Tenant-scoped by construction. The in-memory store backs
tests/offline; the ``feedback`` table (PRD §10) is the durable production store.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class FeedbackAction(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


@dataclass
class CategoryStats:
    accepted: int = 0
    rejected: int = 0
    edited: int = 0

    @property
    def total(self) -> int:
        return self.accepted + self.rejected + self.edited

    @property
    def acceptance_rate(self) -> float:
        """Edited counts as a half-accept (partially useful)."""
        if self.total == 0:
            return 1.0
        return (self.accepted + 0.5 * self.edited) / self.total


class FeedbackStore(Protocol):
    def record(self, tenant_id: str, repo: str, category: str, action: FeedbackAction) -> None: ...

    def stats(self, tenant_id: str, repo: str) -> dict[str, CategoryStats]: ...


class InMemoryFeedbackStore:
    def __init__(self) -> None:
        # tenant -> repo -> category -> stats
        self._data: dict[str, dict[str, dict[str, CategoryStats]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(CategoryStats))
        )

    def record(self, tenant_id: str, repo: str, category: str, action: FeedbackAction) -> None:
        stats = self._data[tenant_id][repo][category]
        if action is FeedbackAction.ACCEPTED:
            stats.accepted += 1
        elif action is FeedbackAction.REJECTED:
            stats.rejected += 1
        else:
            stats.edited += 1

    def stats(self, tenant_id: str, repo: str) -> dict[str, CategoryStats]:
        return dict(self._data.get(tenant_id, {}).get(repo, {}))


# Convenience for wiring.
_default_store: FeedbackStore = InMemoryFeedbackStore()


def default_store() -> FeedbackStore:
    return _default_store
