"""Deterministic in-memory provider for tests and offline development.

Records the exact request it received (so tests can assert redaction + untrusted-content
wrapping) and returns a scripted response (so tests can exercise output validation,
including malformed/malicious model output). Never makes a network call.
"""

from __future__ import annotations

import json

from app.llm.base import LLMRequest, LLMResponse, LLMUsage, ModelCapabilities


class FakeProvider:
    def __init__(
        self,
        response_text: str | None = None,
        *,
        name: str = "fake",
        error: Exception | None = None,
        cost_micros: int = 0,
    ) -> None:
        # Default: a well-formed empty findings object.
        self._response_text = response_text if response_text is not None else '{"findings": []}'
        self.name = name
        self._error = error  # if set, complete() raises it (to exercise fallback)
        self._cost = cost_micros
        self.last_request: LLMRequest | None = None
        self.call_count = 0

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            context_window=200_000,
            supports_json=True,
            input_cost_per_mtok_micros=self._cost,
            output_cost_per_mtok_micros=self._cost,
        )

    def set_response(self, text: str) -> None:
        self._response_text = text

    def set_findings(self, findings: list[dict[str, object]]) -> None:
        self._response_text = json.dumps({"findings": findings})

    def count_tokens(self, text: str) -> int:
        # Cheap deterministic estimate (~4 chars/token).
        return max(1, len(text) // 4)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        self.call_count += 1
        if self._error is not None:
            raise self._error
        prompt_text = request.system + "".join(m.content for m in request.messages)
        return LLMResponse(
            text=self._response_text,
            model="fake-1",
            usage=LLMUsage(
                input_tokens=self.count_tokens(prompt_text),
                output_tokens=self.count_tokens(self._response_text),
            ),
        )
