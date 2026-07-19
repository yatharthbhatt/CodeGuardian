"""Anthropic Claude adapter (PRD §12).

Uses the async Anthropic SDK. Model ids and defaults follow the current Claude line;
swap ``model`` to route by cost/capability. Kept behind the :class:`LLMProvider`
interface so nothing else in the codebase depends on Anthropic directly.

Note: this makes a network call, so it is never exercised in the offline test suite —
tests use :class:`app.llm.providers.fake.FakeProvider`.
"""

from __future__ import annotations

from app.llm.base import LLMRequest, LLMResponse, LLMUsage, ModelCapabilities
from app.llm.errors import ProviderOutageError, RateLimitError

# Default to a strong, current Claude model for the reasoning-heavy review task.
_DEFAULT_MODEL = "claude-sonnet-5"


class ClaudeProvider:
    name = "claude"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        # Imported lazily so the package is optional for Phase-0-only installs.
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=200_000,
            supports_json=True,
            input_cost_per_mtok_micros=3_000_000,
            output_cost_per_mtok_micros=15_000_000,
            supports_prompt_cache=True,
        )

    def count_tokens(self, text: str) -> int:
        # Conservative estimate; exact counting can use the SDK's token API if needed.
        return max(1, len(text) // 4)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # We instruct JSON-only output via the system prompt (see prompting.py) and
        # prefill the assistant turn with "{" to strongly bias valid JSON.
        messages = [{"role": m.role.value, "content": m.content} for m in request.messages]
        if request.expect_json:
            messages.append({"role": "assistant", "content": "{"})

        # Prompt caching: mark the (large, reused) system block cacheable when hinted.
        system: object = request.system
        if request.cache_system:
            system = [
                {
                    "type": "text",
                    "text": request.system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        try:
            resp = await self._client.messages.create(
                model=self._model,
                system=system,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "ratelimit" in name:
                raise RateLimitError(str(exc)) from exc
            if any(k in name for k in ("connection", "timeout", "apistatus", "internal")):
                raise ProviderOutageError(str(exc)) from exc
            raise
        text = "".join(block.text for block in resp.content if block.type == "text")
        if request.expect_json and not text.lstrip().startswith("{"):
            text = "{" + text  # restore the prefill we injected
        return LLMResponse(
            text=text,
            model=resp.model,
            usage=LLMUsage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
            ),
        )
