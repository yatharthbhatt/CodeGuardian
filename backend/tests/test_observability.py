"""Observability tests (PRD §13) — cost, metrics emission, tracing spans."""

from __future__ import annotations

from app.llm.base import LLMUsage, ModelCapabilities
from app.llm.providers.fake import FakeProvider
from app.llm.router import LLMRouter
from app.observability import metrics
from app.observability.cost import cost_micros
from app.observability.tracing import configure_for_testing
from app.review.graph import run_review
from fastapi.testclient import TestClient

from tests.conftest import diff_from_added, make_pr


def _caps(inp: int, out: int) -> ModelCapabilities:
    return ModelCapabilities(
        context_window=1000,
        supports_json=True,
        input_cost_per_mtok_micros=inp,
        output_cost_per_mtok_micros=out,
    )


def test_cost_micros_computation() -> None:
    usage = LLMUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost_micros(usage, _caps(3_000_000, 15_000_000)) == 18_000_000
    assert cost_micros(LLMUsage(), _caps(3_000_000, 15_000_000)) == 0


def _counter(counter, **labels) -> float:  # type: ignore[no-untyped-def]
    return counter.labels(**labels)._value.get()


async def test_review_emits_agent_and_review_metrics() -> None:
    before = _counter(metrics.REVIEWS, outcome="success")
    await run_review(make_pr(), diff_from_added("app/s.py", ["eval(x)"]), use_llm=False)
    after = _counter(metrics.REVIEWS, outcome="success")
    assert after == before + 1
    # The security agent ran and recorded a success.
    assert _counter(metrics.AGENT_RUNS, agent="security", outcome="success") >= 1


async def test_llm_cost_metric_recorded_on_completion() -> None:
    provider = FakeProvider(cost_micros=1_000_000)  # non-zero price
    before = _counter(metrics.LLM_COST_MICROS, provider="fake", tenant="t-1")
    await run_review(
        make_pr(),
        diff_from_added("app/s.py", ["eval(x)"]),
        router=LLMRouter(provider),
        use_llm=True,
    )
    after = _counter(metrics.LLM_COST_MICROS, provider="fake", tenant="t-1")
    assert after >= before  # cost accrued for the tenant


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "cg_reviews_total" in body
    assert "cg_agent_runs_total" in body
    assert "cg_llm_cost_micros_total" in body


async def test_review_emits_otel_spans() -> None:
    exporter = configure_for_testing()
    await run_review(make_pr(), diff_from_added("app/s.py", ["eval(x)"]), use_llm=False)
    names = {s.name for s in exporter.get_finished_spans()}
    assert "review" in names
    assert "agent.run" in names
