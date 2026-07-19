"""Request-id middleware.

Assigns a correlation id to every request (honoring an inbound ``X-Request-ID`` if it
is well-formed, otherwise minting a UUID4), binds it to the logging context, and echoes
it back on the response so clients and traces can correlate. Inbound ids are validated
to prevent log-injection via a hostile header value.
"""

from __future__ import annotations

import re
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import request_id_var

_HEADER = "X-Request-ID"
# Only accept safe, bounded ids from clients (no newlines/control chars → no log injection).
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


class RequestIdMiddleware:
    """Pure-ASGI middleware so it composes cleanly and adds negligible overhead."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        inbound = request.headers.get(_HEADER, "")
        request_id = inbound if _SAFE_ID.match(inbound) else uuid.uuid4().hex
        token = request_id_var.set(request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((_HEADER.encode(), request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)
