"""OpenAI adapter (PRD §12).

Uses the official OpenAI SDK's Chat Completions API. Network-backed; not exercised by the
offline unit suite. Maps SDK errors to normalized provider errors so the router can fail over.
"""

from __future__ import annotations

from app.llm.base import LLMRequest, LLMResponse, LLMUsage, ModelCapabilities
from app.llm.errors import ProviderOutageError, RateLimitError

_DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=128_000,
            supports_json=True,
            input_cost_per_mtok_micros=2_500_000,
            output_cost_per_mtok_micros=10_000_000,
            supports_prompt_cache=True,
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        messages = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role.value, "content": m.content} for m in request.messages]
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                response_format={"type": "json_object"} if request.expect_json else None,
            )
        except Exception as exc:
            raise _map_error(exc) from exc
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        return LLMResponse(
            text=text,
            model=resp.model,
            usage=LLMUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )


def _map_error(exc: Exception) -> Exception:
    name = type(exc).__name__.lower()
    if "ratelimit" in name:
        return RateLimitError(str(exc))
    if any(k in name for k in ("connection", "timeout", "apierror", "internalserver")):
        return ProviderOutageError(str(exc))
    return exc
