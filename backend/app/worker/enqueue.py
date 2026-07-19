"""Enqueuer seam.

The webhook endpoint calls an ``Enqueuer`` after validating a payload. This indirection
lets us (a) run the API with no broker in dev/tests and (b) assert enqueue behavior in
tests without Celery. Production wires it to the Celery task.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.config import Settings

log = logging.getLogger("codeguardian.enqueue")


class Enqueuer(Protocol):
    def __call__(self, payload: dict[str, Any]) -> None: ...


def _noop_enqueuer(payload: dict[str, Any]) -> None:
    log.info("enqueue disabled; review not dispatched", extra={"enqueued": False})


def build_enqueuer(settings: Settings) -> Enqueuer:
    if not settings.enqueue_reviews:
        return _noop_enqueuer

    def _celery_enqueuer(payload: dict[str, Any]) -> None:
        # Imported lazily so Celery/Redis are only required when enqueue is enabled.
        from app.worker.tasks import review_pull_request

        review_pull_request.delay(payload)

    return _celery_enqueuer
