"""Structured logging configuration for the backend.

Audit B-IMP-4: production logs were ad-hoc, with no request IDs and no
JSON formatting. This module gives every log line three pieces:

1. **A request-scoped ID** (``request_id``) so a single user's request
   can be traced through ``routes.py`` -> services -> repository.
2. **JSON-line output** so a log aggregator (Loki, ELK, CloudWatch)
   can index it without parsing free-form text.
3. **An ISO-8601 timestamp** with timezone.

The request ID is propagated via a ``contextvars.ContextVar``, which
asyncio and Starlette honour correctly across awaits (a plain global
would leak across concurrent requests).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# The active request's ID. Set by RequestIdMiddleware at the top of every
# request scope; read by JsonFormatter and by any code that wants to
# correlate its own logs with the request.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Emit each record as a single-line JSON object."""

    # Keys we never want to forward — they're internal to the logging module
    # and would just bloat every record.
    _RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach the request ID when there is one; nothing if we're outside a
        # request scope (e.g. startup, scheduled tasks).
        rid = request_id_ctx.get()
        if rid:
            payload["request_id"] = rid

        # Forward any extra fields the caller passed via ``logger.info(..., extra={...})``.
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and key not in payload and not key.startswith("_"):
                # Make sure the value is JSON-serialisable; fall back to str().
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Idempotently configure the root logger for JSON-line output.

    Calling this multiple times (e.g. in tests) replaces the handler
    rather than stacking new ones.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Drop any previously-installed handlers so re-configuration produces
    # exactly one output stream.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)

    # Quiet uvicorn's default duplicate access log; the middleware emits its
    # own structured request log entry per response.
    logging.getLogger("uvicorn.access").setLevel("WARNING")


# Inbound request IDs are reflected into the response header, the logging
# contextvar, and every JSON log line, so they must stay boring: a bounded
# length of URL-safe characters. Anything else gets a minted UUID instead
# (audit B11 — reject-and-mint rather than truncate, because truncating an
# arbitrary latin-1 string can still smuggle hostile bytes into the logs).
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def sanitize_request_id(value: str | None) -> str | None:
    """Return ``value`` only when it is a safe trace id, else ``None``."""
    if value and _REQUEST_ID_RE.fullmatch(value):
        return value
    return None


class RequestIdMiddleware:
    """ASGI middleware that injects an X-Request-ID per request.

    Reads an inbound ``X-Request-ID`` header if the client already supplied
    one (useful for tracing across services); otherwise generates a fresh
    UUIDv4. Inbound IDs are sanitized first — see ``sanitize_request_id``.
    The ID is stored in ``request_id_ctx`` for the duration of the request
    and added to the response headers so the caller can correlate.
    """

    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("app.request")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Pull X-Request-ID from inbound headers if present; mint one when the
        # header is absent or fails sanitization (overlong / hostile charset).
        inbound: str | None = None
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                inbound = value.decode("latin-1")
                break
        rid = sanitize_request_id(inbound) or uuid.uuid4().hex
        token = request_id_ctx.set(rid)

        method = scope.get("method", "-")
        path = scope.get("path", "-")
        status_holder: dict[str, int] = {}

        # Wrap the send callable so we can inject the X-Request-ID response header
        # and capture the final status for the structured access log below.
        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status")
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", rid.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # Structured access log that actually replaces uvicorn's quieted default
            # (previously claimed but never emitted — self.logger was dead). Carries
            # the request id so one request is greppable end to end.
            self.logger.info(
                "request",
                extra={"method": method, "path": path, "status": status_holder.get("status")},
            )
            request_id_ctx.reset(token)
