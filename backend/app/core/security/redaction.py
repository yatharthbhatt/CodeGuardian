"""Secret / PII redaction.

Two jobs (PRD §9.3 and §9.6):

1. **Log redaction** — no secrets, tokens, or PII may reach logs.
2. **Pre-LLM scrub** — detected secrets are masked *before* any repository content is
   sent to a model provider, so credentials in a diff never leave our trust boundary.

This is intentionally dependency-free and deterministic so it can run everywhere
(logging filters, the LLM adapter, tests). It is a defense-in-depth layer; the
Security Agent's dedicated scanners (Gitleaks/Trufflehog) remain the primary detector.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

MASK: Final[str] = "***REDACTED***"

# Keys whose values must never be logged, regardless of content.
_SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "authorization",
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "private_key",
        "client_secret",
        "webhook_secret",
        "x-hub-signature",
        "x-hub-signature-256",
        "cookie",
        "set-cookie",
    }
)

# High-signal secret patterns. Ordered; each is applied to free text.
_SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # GitHub tokens: ghp_, gho_, ghu_, ghs_, ghr_ + 36+ base62
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    # GitHub fine-grained PAT
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    # OpenAI keys
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    # Anthropic keys
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    # AWS access key id
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Google API key
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    # Slack token
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    # Private key blocks
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ),
    # JWTs (three base64url segments)
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")),
    # Generic bearer header value
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{12,}\b")),
    # Basic auth in URLs: scheme://user:pass@host
    ("url_credentials", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^\s:@/]+:[^\s:@/]+@")),
)

_MAX_SCAN_CHARS: Final[int] = 2_000_000  # cap regex work on huge blobs (ReDoS/DoS guard)


def redact_text(text: str) -> str:
    """Return ``text`` with any detected secrets replaced by :data:`MASK`."""
    if not text:
        return text
    scanned = text[:_MAX_SCAN_CHARS]
    for _name, pattern in _SECRET_PATTERNS:
        if pattern is _SECRET_PATTERNS[-1][1]:  # url_credentials keeps the scheme
            scanned = pattern.sub(rf"\1{MASK}@", scanned)
        else:
            scanned = pattern.sub(MASK, scanned)
    if len(text) > _MAX_SCAN_CHARS:
        scanned += text[_MAX_SCAN_CHARS:]
    return scanned


def _is_sensitive_key(key: str) -> bool:
    return key.strip().lower() in _SENSITIVE_KEYS


def redact_mapping(data: Mapping[str, Any], _depth: int = 0) -> dict[str, Any]:
    """Recursively redact a dict: mask sensitive *keys* and scrub secret *values*."""
    if _depth > 12:  # guard against pathological nesting
        return {"_": MASK}
    out: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(str(key)):
            out[key] = MASK
        else:
            out[key] = redact_value(value, _depth + 1)
    return out


def scan_secret_types(text: str) -> list[str]:
    """Return the *names* of secret types detected in ``text`` (never the values).

    Used by the Security Agent as a deterministic secret detector. Returns type names
    only so we never store or surface the credential itself.
    """
    if not text:
        return []
    scanned = text[:_MAX_SCAN_CHARS]
    found: list[str] = []
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(scanned):
            found.append(name)
    return found


def redact_value(value: Any, _depth: int = 0) -> Any:
    """Redact an arbitrary JSON-ish value."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return redact_mapping(value, _depth)
    if isinstance(value, (list, tuple)):
        return [redact_value(v, _depth + 1) for v in value]
    return value
