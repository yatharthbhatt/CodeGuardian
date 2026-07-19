"""GitHub App authentication (PRD §9.1, rule #5).

We authenticate as a GitHub **App** and mint **short-lived installation tokens** — never
long-lived PATs. The app JWT is RS256-signed by the app's private key (from the secret
manager) and is valid for ≤10 minutes; installation tokens live ~1 hour and are requested
per job, then discarded.
"""

from __future__ import annotations

import time

import jwt

# GitHub rejects app JWTs with lifetime > 10 minutes; stay safely under it.
_MAX_JWT_TTL = 540  # 9 minutes
_CLOCK_SKEW = 60


class GitHubAppAuth:
    def __init__(self, app_id: str, private_key_pem: str) -> None:
        self._app_id = app_id
        self._private_key = private_key_pem

    def app_jwt(self, now: int | None = None, ttl: int = _MAX_JWT_TTL) -> str:
        """Mint a short-lived RS256 app JWT."""
        issued = int(now if now is not None else time.time())
        ttl = min(ttl, _MAX_JWT_TTL)
        payload = {
            # Backdate iat to tolerate minor clock skew (GitHub recommends this).
            "iat": issued - _CLOCK_SKEW,
            "exp": issued + ttl,
            "iss": self._app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def installation_token(self, installation_id: int, http: InstallationTokenClient) -> str:
        """Exchange the app JWT for a short-lived installation access token."""
        return await http.fetch_installation_token(self.app_jwt(), installation_id)


class InstallationTokenClient:
    """Seam for the network call, so auth logic is unit-testable without GitHub."""

    async def fetch_installation_token(self, app_jwt: str, installation_id: int) -> str:
        raise NotImplementedError
