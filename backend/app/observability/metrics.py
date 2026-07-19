"""Prometheus metrics (PRD §13, rule #10).

A single registry with the platform's golden signals: HTTP request rate/errors, review
queue depth, per-agent latency + success/error, and LLM token/cost usage. Everything is
label-scoped so Grafana can slice by agent / provider / tenant. Metric *values* never
contain secrets or PII — only ids and counts.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry()

# --- HTTP ------------------------------------------------------------------
HTTP_REQUESTS = Counter(
    "cg_http_requests_total",
    "HTTP requests",
    labelnames=("method", "route", "status"),
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "cg_http_request_seconds",
    "HTTP request latency",
    labelnames=("method", "route"),
    registry=REGISTRY,
)

# --- Reviews / queue -------------------------------------------------------
REVIEWS = Counter(
    "cg_reviews_total",
    "Completed reviews",
    labelnames=("outcome",),  # success | error
    registry=REGISTRY,
)
REVIEW_LATENCY = Histogram(
    "cg_review_seconds",
    "End-to-end review latency",
    registry=REGISTRY,
)
QUEUE_DEPTH = Gauge(
    "cg_review_queue_depth",
    "Reviews waiting in the queue",
    registry=REGISTRY,
)

# --- Agents ----------------------------------------------------------------
AGENT_LATENCY = Histogram(
    "cg_agent_seconds",
    "Per-agent run latency",
    labelnames=("agent",),
    registry=REGISTRY,
)
AGENT_RUNS = Counter(
    "cg_agent_runs_total",
    "Agent runs",
    labelnames=("agent", "outcome"),  # success | error
    registry=REGISTRY,
)

# --- LLM cost / tokens -----------------------------------------------------
LLM_TOKENS = Counter(
    "cg_llm_tokens_total",
    "LLM tokens consumed",
    labelnames=("provider", "agent", "kind"),  # kind = input | output
    registry=REGISTRY,
)
LLM_COST_MICROS = Counter(
    "cg_llm_cost_micros_total",
    "LLM cost in USD micros",
    labelnames=("provider", "tenant"),
    registry=REGISTRY,
)


def render() -> bytes:
    """Prometheus exposition-format bytes for the ``/metrics`` endpoint."""
    return generate_latest(REGISTRY)
