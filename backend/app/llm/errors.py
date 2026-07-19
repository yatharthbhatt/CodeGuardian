"""Normalized LLM provider errors (PRD §12).

Adapters map their SDK-specific exceptions onto these so the router can make provider-
agnostic decisions (e.g. fail over on a rate-limit or outage).
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for any recoverable provider failure (triggers fallback)."""


class RateLimitError(ProviderError):
    """Provider returned 429 / quota exceeded."""


class ProviderOutageError(ProviderError):
    """Provider is unreachable or returned 5xx."""
