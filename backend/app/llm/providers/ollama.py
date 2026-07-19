"""Local Ollama adapter (PRD §12).

Talks to a local Ollama server over HTTP (no API key, zero marginal cost, on-prem/private).
Great for air-gapped or cost-sensitive deployments. Network-backed (localhost).
"""

from __future__ import annotations

from app.llm.base import LLMRequest, LLMResponse, LLMUsage, ModelCapabilities
from app.llm.errors import ProviderOutageError

_DEFAULT_MODEL = "llama3.1"


class OllamaProvider:
    name = "ollama"

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = _DEFAULT_MODEL
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    @property
    def capabilities(self) -> ModelCapabilities:
        # Local model: no per-token cost.
        return ModelCapabilities(
            context_window=128_000,
            supports_json=True,
            input_cost_per_mtok_micros=0,
            output_cost_per_mtok_micros=0,
        )

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        import httpx

        messages = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role.value, "content": m.content} for m in request.messages]
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        if request.expect_json:
            payload["format"] = "json"
        try:
            async with httpx.AsyncClient(timeout=120) as http:
                resp = await http.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise ProviderOutageError(str(exc)) from exc
        return LLMResponse(
            text=data.get("message", {}).get("content", ""),
            model=self._model,
            usage=LLMUsage(
                input_tokens=int(data.get("prompt_eval_count", 0)),
                output_tokens=int(data.get("eval_count", 0)),
            ),
        )
