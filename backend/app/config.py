"""Application settings.

Security rule #2 (PRD §9.6): **no secrets in code**. Every sensitive value is loaded
from the environment (in production, injected from a secret manager such as Vault/KMS —
never committed). `SecretStr` prevents secrets from leaking into logs/reprs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central, validated configuration.

    Values come from environment variables (case-insensitive) or a local `.env`
    file for development only. See `.env.example` for the full documented list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CG_",
        case_sensitive=False,
        extra="forbid",  # reject unknown env vars — fail fast, no silent typos
    )

    # --- Runtime ------------------------------------------------------------
    environment: Literal["development", "staging", "production", "test"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    service_name: str = "codeguardian-api"

    # --- Datastores (DSNs only; credentials belong in the DSN from secret mgr) --
    database_url: str = "sqlite+pysqlite:///:memory:"
    redis_url: str = "redis://localhost:6379/0"

    # --- GitHub webhook security (PRD §9.1) --------------------------------
    # The shared secret configured on the GitHub App/webhook. Required to verify
    # HMAC signatures. Never logged.
    github_webhook_secret: SecretStr = Field(default=SecretStr(""))
    # Reject webhook deliveries older than this many seconds (replay window).
    webhook_replay_window_seconds: int = 300
    # Max accepted webhook body size (bytes) — cheap DoS guard before parsing.
    webhook_max_body_bytes: int = 5 * 1024 * 1024  # 5 MiB

    # --- Async worker ------------------------------------------------------
    # When true, validated webhooks are enqueued to Celery. Off in tests/dev so no
    # broker is required to run the API.
    enqueue_reviews: bool = False

    # --- GitHub App auth (Phase 1; declared here so config is complete) -----
    github_app_id: str | None = None
    github_app_private_key: SecretStr | None = None

    # --- LLM providers (Phase 1) -------------------------------------------
    anthropic_api_key: SecretStr | None = None
    # Hard ceiling on tokens spent reviewing a single PR (economic-DoS guard, PRD §9.5).
    per_pr_token_budget: int = 120_000

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def require_webhook_secret(self) -> str:
        """Return the webhook secret or fail loudly.

        In production a missing secret is a hard error — we never fall back to
        an unauthenticated webhook path.
        """
        secret = self.github_webhook_secret.get_secret_value()
        if not secret and self.is_production:
            raise RuntimeError("CG_GITHUB_WEBHOOK_SECRET is required in production but is unset.")
        return secret


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (import-safe, test-overridable via env)."""
    return Settings()
