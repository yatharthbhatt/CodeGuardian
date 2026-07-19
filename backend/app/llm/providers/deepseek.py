"""DeepSeek adapter (PRD §12).

DeepSeek exposes an OpenAI-compatible API, so we reuse the OpenAI SDK pointed at DeepSeek's
base URL. Cheap model → good default for high-volume triage. Network-backed.
"""

from __future__ import annotations

from app.llm.base import LLMRequest, LLMResponse, LLMUsage, ModelCapabilities
from app.llm.errors import ProviderOutageError, RateLimitError

_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=_BASE_URL)
        self._model = model

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=64_000,
            supports_json=True,
            input_cost_per_mtok_micros=270_000,
            output_cost_per_mtok_micros=1_100_000,
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
            )
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "ratelimit" in name:
                raise RateLimitError(str(exc)) from exc
            raise ProviderOutageError(str(exc)) from exc
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
