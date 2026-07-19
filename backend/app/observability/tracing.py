"""OpenTelemetry tracing (PRD §13).

One trace per pull request spanning webhook → review → agents → publish. Tracing is
configured once via :func:`init_tracing`; if OpenTelemetry isn't installed or configured,
:func:`span` degrades to a no-op context manager so the review path never depends on it.

Tests install an in-memory span exporter (see ``configure_for_testing``) and assert the
expected spans are emitted.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_TRACER: Any | None = None


def init_tracing(service_name: str = "codeguardian", exporter: Any | None = None) -> None:
    """Configure a tracer provider. ``exporter`` defaults to none (no-op) — production
    wires an OTLP exporter; tests pass an in-memory one."""
    global _TRACER
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    except ImportError:  # opentelemetry not installed → stay no-op
        _TRACER = None
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """Start a span if tracing is configured; otherwise a no-op."""
    if _TRACER is None:
        yield
        return
    with _TRACER.start_as_current_span(name) as s:
        for key, value in attributes.items():
            s.set_attribute(key, value)
        yield


def configure_for_testing() -> Any:
    """Install an in-memory exporter and return it (for assertions in tests)."""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    init_tracing(exporter=exporter)
    return exporter
