"""LLM provider abstraction (PRD §12, rule #11) — no vendor lock-in.

Every model call goes through :class:`LLMProvider`. A per-review :class:`TokenBudget`
enforces a hard ceiling so a single PR can never trigger runaway spend (economic-DoS
guard, PRD §9.5). Providers return typed usage so cost telemetry is exact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role
    content: str


@dataclass(frozen=True)
class ModelCapabilities:
    context_window: int
    supports_json: bool
    input_cost_per_mtok_micros: int  # USD micros per 1M input tokens
    output_cost_per_mtok_micros: int
    supports_prompt_cache: bool = False

    @property
    def blended_cost_micros(self) -> int:
        """A rough per-1M-token cost for cheapest-first routing (input-weighted)."""
        return self.input_cost_per_mtok_micros * 3 + self.output_cost_per_mtok_micros


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: str
    messages: list[LLMMessage]
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    # When set, the provider is asked to return JSON conforming to this shape.
    expect_json: bool = True
    # Hint that the (large, reused) system block is worth caching where supported.
    cache_system: bool = False


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    text: str
    model: str
    usage: LLMUsage


class BudgetExceededError(Exception):
    """Raised when a request would exceed the per-review token budget."""


@dataclass
class TokenBudget:
    """Hard per-review token ceiling. Charged after every call; also tracks cost."""

    limit: int
    used: int = 0
    cost_micros: int = 0
    _by_agent: dict[str, int] = field(default_factory=dict)
    _cost_by_agent: dict[str, int] = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    def precheck(self, estimated_tokens: int) -> None:
        if self.used + estimated_tokens > self.limit:
            raise BudgetExceededError(
                f"budget {self.limit} would be exceeded (used {self.used}, +{estimated_tokens})"
            )

    def charge(self, usage: LLMUsage, agent: str = "unknown", cost_micros: int = 0) -> None:
        self.used += usage.total
        self.cost_micros += cost_micros
        self._by_agent[agent] = self._by_agent.get(agent, 0) + usage.total
        self._cost_by_agent[agent] = self._cost_by_agent.get(agent, 0) + cost_micros

    def cost_by_agent(self) -> dict[str, int]:
        return dict(self._cost_by_agent)

    def tokens_by_agent(self) -> dict[str, int]:
        return dict(self._by_agent)


@runtime_checkable
class LLMProvider(Protocol):
    """Adapter interface every model backend implements."""

    name: str

    @property
    def capabilities(self) -> ModelCapabilities: ...

    def count_tokens(self, text: str) -> int: ...

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
