"""Google Gemini adapter (PRD §12).

Uses the google-genai SDK. Network-backed; not exercised by the offline unit suite.
"""

from __future__ import annotations

from app.llm.base import LLMRequest, LLMResponse, LLMUsage, ModelCapabilities
from app.llm.errors import ProviderOutageError, RateLimitError

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=1_000_000,
            supports_json=True,
            input_cost_per_mtok_micros=100_000,
            output_cost_per_mtok_micros=400_000,
            supports_prompt_cache=True,
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        from google.genai import types

        prompt = "\n\n".join(m.content for m in request.messages)
        try:
            resp = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=request.system,
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature,
                    response_mime_type="application/json" if request.expect_json else None,
                ),
            )
        except Exception as exc:
            name = type(exc).__name__.lower()
            if "resourceexhausted" in name or "ratelimit" in name:
                raise RateLimitError(str(exc)) from exc
            raise ProviderOutageError(str(exc)) from exc
        usage = resp.usage_metadata
        return LLMResponse(
            text=resp.text or "",
            model=self._model,
            usage=LLMUsage(
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            ),
        )
