"""LLM cost computation (PRD §13 — cost per PR / agent / tenant)."""

from __future__ import annotations

from app.llm.base import LLMUsage, ModelCapabilities


def cost_micros(usage: LLMUsage, capabilities: ModelCapabilities) -> int:
    """USD micros for a single call given token usage and the model's per-Mtok prices."""
    inp = usage.input_tokens / 1_000_000 * capabilities.input_cost_per_mtok_micros
    out = usage.output_tokens / 1_000_000 * capabilities.output_cost_per_mtok_micros
    return round(inp + out)
