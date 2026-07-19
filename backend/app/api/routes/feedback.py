"""Feedback ingestion endpoint (PRD §16, §8.12, §9.2, §9.8).

Developers' accept/reject/edit signals feed the Golden-Path learner. Hardened in Phase 6:
requires an authenticated **member+** principal, the tenant is taken from the **token**
(never the body — no cross-tenant writes), and every submission is written to the
immutable audit log.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.auth import Principal, require_role
from app.api.deps import get_feedback_store
from app.core.security.rbac import Role
from app.feedback.store import FeedbackAction, FeedbackStore

router = APIRouter(prefix="/api/v1", tags=["feedback"])

_Cat = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
_Member = Annotated[Principal, Depends(require_role(Role.MEMBER))]


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repo: Annotated[str, StringConstraints(max_length=512, pattern=r"^[^/]+/[^/]+$")]
    category: _Cat
    action: FeedbackAction


@router.post("/feedback")
async def submit_feedback(
    body: FeedbackIn,
    request: Request,
    principal: _Member,
    store: FeedbackStore = Depends(get_feedback_store),
) -> dict[str, str]:
    # Tenant comes from the authenticated principal — never a client-supplied value.
    store.record(principal.tenant_id, body.repo, body.category, body.action)
    request.app.state.audit_store.record(
        principal.tenant_id,
        actor=principal.user,
        action="feedback.record",
        detail={"repo": body.repo, "category": body.category, "action": body.action.value},
    )
    return {"status": "recorded"}
