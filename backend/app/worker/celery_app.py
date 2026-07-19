"""Celery application (PRD §4 — async worker).

Redis broker/backend. Configured for at-least-once delivery with idempotent tasks:
``acks_late`` + ``reject_on_worker_lost`` so a crashed worker re-queues, and the task
itself is idempotent on the review key, so duplicates are harmless.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "codeguardian",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_default_queue="reviews",
)
