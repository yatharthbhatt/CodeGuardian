"""Settings/config tests (PRD §9.6 — secrets never leak, fail closed in prod)."""

from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import SecretStr, ValidationError


def test_secret_not_in_repr() -> None:
    s = Settings(github_webhook_secret=SecretStr("supersecret"))
    assert "supersecret" not in repr(s)
    assert "supersecret" not in str(s.github_webhook_secret)


def test_unknown_env_var_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(totally_unknown_field="x")  # type: ignore[call-arg]


def test_require_webhook_secret_raises_in_production_when_missing() -> None:
    s = Settings(environment="production", github_webhook_secret=SecretStr(""))
    with pytest.raises(RuntimeError):
        s.require_webhook_secret()


def test_require_webhook_secret_ok_when_present() -> None:
    s = Settings(environment="production", github_webhook_secret=SecretStr("abc"))
    assert s.require_webhook_secret() == "abc"
