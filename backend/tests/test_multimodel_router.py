"""Multi-model router: fallback, cost routing, budget safety (PRD §12, §9.5)."""

from __future__ import annotations

import pytest
from app.llm.base import BudgetExceededError, LLMMessage, LLMRequest, Role, TokenBudget
from app.llm.errors import ProviderError, RateLimitError
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter


def _req() -> LLMRequest:
    return LLMRequest(system="sys", messages=[LLMMessage(role=Role.USER, content="hi")])


async def test_falls_over_to_secondary_on_rate_limit() -> None:
    primary = FakeProvider(name="primary", error=RateLimitError("429"))
    secondary = FakeProvider('{"findings": []}', name="secondary")
    router = LLMRouter(primary, fallbacks=[secondary])

    resp = await router.complete(_req(), budget=TokenBudget(limit=100_000), agent="t")
    assert resp.model == "fake-1"
    assert secondary.call_count == 1
    assert primary.call_count == 1


async def test_raises_when_all_providers_fail() -> None:
    a = FakeProvider(name="a", error=RateLimitError("429"))
    b = FakeProvider(name="b", error=ProviderError("down"))
    router = LLMRouter(a, fallbacks=[b])
    with pytest.raises(ProviderError):
        await router.complete(_req(), budget=TokenBudget(limit=100_000), agent="t")


async def test_cheapest_selection() -> None:
    pricey = FakeProvider(name="pricey", cost_micros=3_000_000)
    cheap = FakeProvider(name="cheap", cost_micros=100_000)
    router = LLMRouter(pricey, fallbacks=[cheap])
    assert router.cheapest().name == "cheap"


async def test_prefer_cheap_routes_to_cheapest_first() -> None:
    pricey = FakeProvider(name="pricey", cost_micros=3_000_000)
    cheap = FakeProvider(name="cheap", cost_micros=100_000)
    router = LLMRouter(pricey, fallbacks=[cheap])
    await router.complete(_req(), budget=TokenBudget(limit=100_000), agent="t", prefer_cheap=True)
    assert cheap.call_count == 1
    assert pricey.call_count == 0


async def test_budget_is_not_bypassed_by_fallback() -> None:
    # A hard budget breach must raise (economic-DoS guard), never silently fail over.
    primary = FakeProvider(name="primary", error=RateLimitError("429"))
    secondary = FakeProvider(name="secondary")
    router = LLMRouter(primary, fallbacks=[secondary])
    with pytest.raises(BudgetExceededError):
        await router.complete(_req(), budget=TokenBudget(limit=1), agent="t")


async def test_explicit_provider_selection() -> None:
    a = FakeProvider(name="a")
    b = FakeProvider('{"x": 1}', name="b")
    router = LLMRouter(a, fallbacks=[b])
    await router.complete(_req(), budget=TokenBudget(limit=100_000), agent="t", provider="b")
    assert b.call_count == 1
