"""GitHub webhook ingress — the primary, security-critical entrypoint (PRD §4, §9).

Order of defenses (fail-closed at each step):
  1. Body-size cap        → cheap DoS guard before we read/parse anything.
  2. HMAC verification    → authenticate the sender (constant-time compare).
  3. Replay guard         → reject duplicate/replayed delivery ids.
  4. Strict validation    → Pydantic models reject malformed/hostile payloads.
  5. Enqueue (idempotent) → hand off to the async worker (Phase 1); Phase 0 ack's.

We never parse the JSON *before* verifying the signature, and we sign/verify over the
exact received bytes.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.deps import get_enqueuer, get_replay_guard, get_settings_dep
from app.config import Settings
from app.core.security.webhook import (
    ReplayError,
    ReplayGuard,
    SignatureError,
    verify_signature,
)
from app.schemas.github import PullRequestEvent
from app.worker.enqueue import Enqueuer

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger("codeguardian.webhook")

# Numeric literals to stay stable across Starlette's constant renames (413/422).
_HTTP_413 = 413
_HTTP_422 = 422


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
    replay_guard: ReplayGuard = Depends(get_replay_guard),
    enqueue: Enqueuer = Depends(get_enqueuer),
) -> Response:
    # 1) Size cap BEFORE reading the whole body into memory.
    max_bytes = settings.webhook_max_body_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        return _problem(_HTTP_413, "payload too large")

    body = await request.body()
    if len(body) > max_bytes:
        return _problem(_HTTP_413, "payload too large")

    # 2) Authenticate the sender via HMAC over the raw bytes.
    secret = settings.require_webhook_secret()
    try:
        verify_signature(secret, body, x_hub_signature_256)
    except SignatureError:
        # Do NOT echo details — avoid oracles. Log the delivery id only.
        log.warning("webhook signature rejected", extra={"delivery": x_github_delivery})
        return _problem(status.HTTP_401_UNAUTHORIZED, "invalid signature")

    # 3) Replay / duplicate protection keyed on GitHub's per-delivery id.
    try:
        replay_guard.check_and_remember(x_github_delivery)
    except ReplayError:
        # Idempotent: acknowledge duplicates without re-processing.
        log.info("webhook duplicate ignored", extra={"delivery": x_github_delivery})
        return JSONResponse({"status": "duplicate_ignored"}, status_code=status.HTTP_200_OK)

    # 4) Parse + strictly validate. Only after auth so we never parse untrusted-unsigned input.
    try:
        raw = json.loads(body)
    except json.JSONDecodeError:
        return _problem(status.HTTP_400_BAD_REQUEST, "invalid json")
    if not isinstance(raw, dict):
        return _problem(status.HTTP_400_BAD_REQUEST, "invalid payload")

    # Route by event type. Phase 0 handles pull_request; others are acknowledged.
    if x_github_event == "ping":
        return JSONResponse({"status": "pong"}, status_code=status.HTTP_200_OK)

    if x_github_event != "pull_request":
        log.info("webhook event ignored", extra={"event": x_github_event})
        return JSONResponse({"status": "ignored", "event": x_github_event}, status_code=200)

    try:
        event = PullRequestEvent.model_validate(raw)
    except ValidationError as exc:
        log.warning("webhook payload invalid", extra={"errors": exc.error_count()})
        return _problem(_HTTP_422, "payload failed validation")

    if not event.should_review:
        return JSONResponse({"status": "no_review", "action": event.action.value}, status_code=200)

    # 5) Enqueue the async LangGraph review (idempotent on the review key).
    idempotency_key = f"{event.repository.id}:{event.number}:{event.pull_request.head.sha}"
    enqueue(raw)
    # Audit the state-changing action (service principal = GitHub). Tenant is the repo id
    # until it is mapped to a real tenant during installation onboarding (Phase 6 RBAC).
    audit = getattr(request.app.state, "audit_store", None)
    if audit is not None:
        audit.record(
            str(event.repository.id),
            actor="github",
            action="webhook.pr_accepted",
            detail={"repo": event.repository.full_name, "pr": event.number},
        )
    log.info(
        "webhook accepted",
        extra={
            "event": x_github_event,
            "repo": event.repository.full_name,
            "pr": event.number,
            "action": event.action.value,
            "idempotency_key": idempotency_key,
        },
    )
    return JSONResponse(
        {"status": "accepted", "idempotency_key": idempotency_key},
        status_code=status.HTTP_202_ACCEPTED,
    )


def _problem(code: int, detail: str) -> JSONResponse:
    """RFC7807-ish minimal error body (no internal details leaked)."""
    return JSONResponse({"detail": detail}, status_code=code)
