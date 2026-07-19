"""API authentication + authorization (PRD §9.1, §9.2).

Bearer-token auth via a pluggable :class:`TokenVerifier`. Production wires an OIDC/JWT
verifier (validate signature against the IdP's JWKS, map claims → tenant/role); dev/tests
use an in-memory verifier. Every authenticated principal carries a ``tenant_id`` and
``role``; the tenant is taken from the *token*, never from a client-supplied parameter, so
cross-tenant access is impossible by construction. ``require_role`` enforces RBAC.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security.rbac import Role, at_least

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    user: str
    role: Role


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Principal | None: ...


class DevTokenVerifier:
    """In-memory token → principal map for dev/tests (NOT for production)."""

    def __init__(self) -> None:
        self._tokens: dict[str, Principal] = {}

    def add(self, token: str, principal: Principal) -> None:
        self._tokens[token] = principal

    def verify(self, token: str) -> Principal | None:
        return self._tokens.get(token)


def get_token_verifier(request: Request) -> TokenVerifier:
    return request.app.state.token_verifier  # type: ignore[no-any-return]


def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    verifier: TokenVerifier = request.app.state.token_verifier
    principal = verifier.verify(creds.credentials)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return principal


def require_role(minimum: Role) -> Callable[[Principal], Principal]:
    """Dependency factory enforcing a minimum role (RBAC)."""

    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        if not at_least(principal.role, minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return principal

    return _dep
