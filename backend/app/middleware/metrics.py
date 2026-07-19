"""HTTP request metrics middleware (PRD §13).

Records request rate, latency, and status per route. Uses the matched *route template*
(e.g. ``/api/v1/feedback``) rather than the raw path, so metric labels stay low-cardinality.
"""

from __future__ import annotations

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability import metrics


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or scope.get("path", "unknown")
            method = scope.get("method", "GET")
            metrics.HTTP_REQUESTS.labels(method, path, str(status["code"])).inc()
            metrics.HTTP_LATENCY.labels(method, path).observe(time.perf_counter() - start)
