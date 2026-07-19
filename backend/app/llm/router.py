"""Provider registry + budget-enforced completion with routing & fallback (PRD §12, §9.5).

The router is the single seam through which every model call flows. It:
  * enforces the per-review :class:`TokenBudget` (fail closed before overspending),
  * routes to a chosen provider — by name, or cheapest-first for cost-sensitive tasks,
  * fails over to the next provider on a recoverable :class:`ProviderError`
    (rate-limit / outage), so one vendor outage doesn't stop reviews.
"""

from __future__ import annotations

import logging

from app.llm.base import (
    BudgetExceededError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenBudget,
)
from app.llm.errors import ProviderError
from app.observability import metrics
from app.observability.cost import cost_micros

log = logging.getLogger("codeguardian.llm")


class LLMRouter:
    def __init__(self, default: LLMProvider, fallbacks: list[LLMProvider] | None = None) -> None:
        self._providers: dict[str, LLMProvider] = {default.name: default}
        self._default_name = default.name
        # Ordered failover chain (primary first).
        self._chain: list[str] = [default.name]
        for fb in fallbacks or []:
            self.register(fb, fallback=True)

    def register(self, provider: LLMProvider, *, fallback: bool = False) -> None:
        self._providers[provider.name] = provider
        if fallback and provider.name not in self._chain:
            self._chain.append(provider.name)

    def get(self, name: str | None = None) -> LLMProvider:
        return self._providers[name or self._default_name]

    def cheapest(self) -> LLMProvider:
        """Pick the lowest blended-cost registered provider (for cheap tasks like triage)."""
        return min(self._providers.values(), key=lambda p: p.capabilities.blended_cost_micros)

    def _order(self, provider: str | None, prefer_cheap: bool) -> list[str]:
        if provider is not None:
            # Explicit choice, then remaining fallbacks for resilience.
            return [provider] + [n for n in self._chain if n != provider]
        if prefer_cheap:
            first = self.cheapest().name
            return [first] + [n for n in self._chain if n != first]
        return list(self._chain)

    async def complete(
        self,
        request: LLMRequest,
        *,
        budget: TokenBudget,
        agent: str,
        provider: str | None = None,
        prefer_cheap: bool = False,
        tenant: str = "-",
    ) -> LLMResponse:
        order = self._order(provider, prefer_cheap)
        last_error: ProviderError | None = None
        for name in order:
            p = self._providers[name]
            estimate = p.count_tokens(request.system) + sum(
                p.count_tokens(m.content) for m in request.messages
            )
            # Budget is a hard limit and is NOT recoverable — never fail over past it.
            budget.precheck(estimate + request.max_tokens)
            try:
                response = await p.complete(request)
            except ProviderError as exc:
                last_error = exc
                log.warning("provider failed, trying fallback", extra={"provider": name})
                continue
            # Charge tokens + cost, and emit telemetry (labels carry no secrets/PII).
            cost = cost_micros(response.usage, p.capabilities)
            budget.charge(response.usage, agent=agent, cost_micros=cost)
            metrics.LLM_TOKENS.labels(name, agent, "input").inc(response.usage.input_tokens)
            metrics.LLM_TOKENS.labels(name, agent, "output").inc(response.usage.output_tokens)
            metrics.LLM_COST_MICROS.labels(name, tenant).inc(cost)
            return response
        raise last_error or ProviderError("no providers available")


__all__ = ["BudgetExceededError", "LLMRouter", "ProviderError"]
