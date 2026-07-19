"""Redaction tests — no secret may survive a redaction pass (PRD §9.6)."""

from __future__ import annotations

import logging

import pytest
from app.core.security.redaction import MASK, redact_mapping, redact_text
from app.logging_config import JsonFormatter, RedactionFilter


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "A" * 36,
        "github_pat_" + "B" * 40,
        "sk-" + "C" * 40,
        "sk-ant-" + "D" * 40,
        "AKIA" + "1234567890ABCDEF",
        "AIza" + "0123456789012345678901234567890abcd",
        "xoxb-" + "0123456789-abcdef",
    ],
)
def test_secret_patterns_are_masked(secret: str) -> None:
    out = redact_text(f"token is {secret} end")
    assert secret not in out
    assert MASK in out


def test_private_key_block_masked() -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----"
    assert "BEGIN RSA PRIVATE KEY" not in redact_text(text)


def test_url_credentials_masked_but_scheme_kept() -> None:
    out = redact_text("postgres://user:supersecret@db:5432/app")
    assert "supersecret" not in out
    assert out.startswith("postgres://")


def test_sensitive_keys_masked() -> None:
    out = redact_mapping({"Authorization": "Bearer xyz", "nested": {"password": "p"}})
    assert out["Authorization"] == MASK
    assert out["nested"]["password"] == MASK


def test_bearer_value_masked() -> None:
    assert "abcdefghijkl" not in redact_text("Authorization: Bearer abcdefghijklmnop")


def test_log_filter_scrubs_message() -> None:
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="leaking %s",
        args=("ghp_" + "Z" * 36,),
        exc_info=None,
    )
    RedactionFilter().filter(record)
    rendered = JsonFormatter().format(record)
    assert "ghp_" not in rendered
    assert MASK in rendered


def test_log_filter_scrubs_extras() -> None:
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="event",
        args=(),
        exc_info=None,
    )
    record.token = "sk-" + "Q" * 40  # structured extra
    RedactionFilter().filter(record)
    assert "sk-" not in JsonFormatter().format(record)
