"""Transport-level request guards.

Audit SD-3/CI6: the only request-body size cap lived in the compose stack's
nginx (``client_max_body_size``). Anyone running the backend directly —
``uvicorn app.main:app`` per the README, or a future deployment without the
proxy — had no transport cap at all: a client could stream gigabytes into the
multipart spool before the per-endpoint byte budgets ever saw a number.

``RequestSizeLimitMiddleware`` is a pure-ASGI wrap (same shape as
``RequestIdMiddleware``) that enforces the cap in two layers:

1. A declared ``Content-Length`` over the cap is rejected immediately with a
   413, before a single body byte is read.
2. Bodies without a trustworthy declaration (chunked transfer, or a client
   that lies) are counted as ``http.request`` messages arrive; crossing the
   cap aborts the request mid-stream with the same 413.

The 413 is hand-built because this runs outside FastAPI's exception handlers:
the body matches the app-wide ``{"detail": ...}`` envelope, and it carries
``Connection: close`` since an undrained keep-alive connection must not be
reused.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

# The transport cap sits a little above PAPI_MAX_BATCH_UPLOAD_MB so the
# per-endpoint budget (with its precise, actionable message) fires first for
# honest uploads; the headroom absorbs multipart framing overhead. Mirrors the
# nginx pairing (client_max_body_size 410m vs the 400 MB batch budget).
UPLOAD_HEADROOM_MB = 10


def request_body_cap_bytes(settings: Settings) -> int:
    """The transport-level body cap derived from the upload budget."""
    return (settings.max_batch_upload_mb + UPLOAD_HEADROOM_MB) * 1024 * 1024


class _BodyTooLarge(Exception):
    """Internal signal: the streamed body crossed the cap mid-read."""


class RequestSizeLimitMiddleware:
    """Reject request bodies larger than ``max_body_bytes`` with a 413."""

    def __init__(self, app, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Layer 1: a declared Content-Length over the cap is refused outright —
        # the app (and the body) are never touched. A malformed declaration is
        # treated as absent; the streaming counter below still protects.
        declared = self._declared_content_length(scope)
        if declared is not None and declared > self.max_body_bytes:
            await self._send_413(send)
            return

        # Layer 2: count the body as it streams in case the declaration was
        # missing or dishonest. ``response_started`` guards the abort path —
        # once bytes are on the wire we cannot send a second response.
        received = 0
        response_started = False

        async def limited_receive(*args, **kwargs):
            nonlocal received
            message = await receive(*args, **kwargs)
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        # Topology note: ServerErrorMiddleware is the OUTERMOST wrap of the whole
        # Starlette stack (built before user middlewares), so it can never see
        # _BodyTooLarge before this except does — verified empirically on real
        # uvicorn: a chunked over-cap body yields this 413, not a 500. Do not
        # "fix" this by deriving _BodyTooLarge from BaseException.
        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if response_started:
                # Defensive: an app that already responded while still reading
                # the body. Nothing valid can be appended — let the server
                # close the half-written connection.
                logger.warning(
                    "Request body exceeded the %d-byte cap after the response started.",
                    self.max_body_bytes,
                )
                return
            await self._send_413(send)

    @staticmethod
    def _declared_content_length(scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    async def _send_413(self, send) -> None:
        cap_mb = self.max_body_bytes // (1024 * 1024)
        body = json.dumps(
            {
                "detail": (
                    f"Request body exceeds the {cap_mb} MB transport limit. Split the "
                    f"upload and retry, or raise PAPI_MAX_BATCH_UPLOAD_MB on the server."
                )
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
