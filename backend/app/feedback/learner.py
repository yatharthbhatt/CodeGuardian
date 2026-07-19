"""Golden-Path learner (PRD §8.12).

Turns accumulated feedback into per-category confidence *adjustments* the consensus engine
applies. Categories a team routinely **rejects** get down-weighted (so they're suppressed
sooner → less noise); categories they **accept** keep full weight. Needs a minimum number
of samples before it adapts, so it never overreacts to one data point.
"""

from __future__ import annotations

from app.feedback.store import FeedbackStore

_MIN_SAMPLES = 5
_FLOOR = 0.4  # never down-weight a category below 40% of its base confidence


class GoldenPathLearner:
    def __init__(self, store: FeedbackStore, min_samples: int = _MIN_SAMPLES) -> None:
        self._store = store
        self._min_samples = min_samples

    def adjustments(self, tenant_id: str, repo: str) -> dict[str, float]:
        """Return category → confidence multiplier in [floor, 1.0]."""
        out: dict[str, float] = {}
        for category, stats in self._store.stats(tenant_id, repo).items():
            if stats.total < self._min_samples:
                continue  # not enough evidence to adapt
            # acceptance 1.0 → 1.0x ; acceptance 0.0 → floor.
            out[category] = _FLOOR + (1.0 - _FLOOR) * stats.acceptance_rate
        return out
