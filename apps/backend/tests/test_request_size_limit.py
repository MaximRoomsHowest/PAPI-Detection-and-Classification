"""Transport-level request-body cap (audit SD-3/CI6).

Covers the raw ASGI behavior (declared-length fast reject, streamed-body
counting, no-second-response guard), the FastAPI-stack behavior (413 envelope
+ X-Request-ID, chunked clients), and the middleware ordering on the real app.
"""

from __future__ import annotations

import asyncio
import json

from app.logging_config import RequestIdMiddleware
from app.main import app as real_app
from app.middleware import RequestSizeLimitMiddleware, request_body_cap_bytes
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {"type": "http", "method": "POST", "path": "/", "headers": headers or []}


def _collecting_send(sink: list):
    async def send(message):
        sink.append(message)

    return send


# --------------------------------------------------------------------------
# ASGI-unit level
# --------------------------------------------------------------------------


def test_declared_content_length_over_cap_returns_413_without_reading_body():
    async def inner_app(scope, receive, send):
        raise AssertionError("app must not be called for an oversized declaration")

    async def receive():
        raise AssertionError("receive must not be called for an oversized declaration")

    sent: list = []
    middleware = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10)
    scope = _http_scope(headers=[(b"content-length", b"11")])
    asyncio.run(middleware(scope, receive, _collecting_send(sent)))

    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413
    assert (b"connection", b"close") in sent[0]["headers"]
    assert b"transport limit" in sent[1]["body"]


def test_chunked_body_over_cap_aborts_mid_stream():
    """No Content-Length: the cumulative counter must fire mid-read."""
    completed = False

    async def inner_app(scope, receive, send):
        nonlocal completed
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        completed = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    chunks = [
        {"type": "http.request", "body": b"x" * 600, "more_body": True},
        {"type": "http.request", "body": b"x" * 600, "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    sent: list = []
    middleware = RequestSizeLimitMiddleware(inner_app, max_body_bytes=1000)
    asyncio.run(middleware(_http_scope(), receive, _collecting_send(sent)))

    assert completed is False
    assert sent[0]["status"] == 413


def test_under_cap_request_passes_through_unchanged():
    async def inner_app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    chunks = [
        {"type": "http.request", "body": b"x" * 600, "more_body": True},
        {"type": "http.request", "body": b"x" * 300, "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    sent: list = []
    middleware = RequestSizeLimitMiddleware(inner_app, max_body_bytes=1000)
    asyncio.run(middleware(_http_scope(), receive, _collecting_send(sent)))

    assert sent[0]["status"] == 200
    assert sent[1]["body"] == b"ok"


def test_no_second_response_when_app_already_started_sending():
    """If the app responded before the cap fired, nothing more may be sent."""

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        # Keep reading after responding — crosses the cap mid-read.
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    chunks = [
        {"type": "http.request", "body": b"x" * 2000, "more_body": True},
    ]

    async def receive():
        return chunks.pop(0)

    sent: list = []
    middleware = RequestSizeLimitMiddleware(inner_app, max_body_bytes=1000)
    asyncio.run(middleware(_http_scope(), receive, _collecting_send(sent)))

    statuses = [m["status"] for m in sent if m["type"] == "http.response.start"]
    assert statuses == [200]


def test_malformed_content_length_falls_back_to_streaming_counter():
    async def inner_app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    chunks = [{"type": "http.request", "body": b"x" * 2000, "more_body": False}]

    async def receive():
        return chunks.pop(0)

    sent: list = []
    middleware = RequestSizeLimitMiddleware(inner_app, max_body_bytes=1000)
    scope = _http_scope(headers=[(b"content-length", b"not-a-number")])
    asyncio.run(middleware(scope, receive, _collecting_send(sent)))

    assert sent[0]["status"] == 413


# --------------------------------------------------------------------------
# FastAPI stack level (BodyCap inner, RequestId outer — main.py order)
# --------------------------------------------------------------------------


def _stack_app(max_body_bytes: int = 1024) -> FastAPI:
    stack = FastAPI()

    @stack.post("/echo")
    async def echo(request: Request) -> dict:
        body = await request.body()
        return {"received": len(body)}

    stack.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=max_body_bytes)
    stack.add_middleware(RequestIdMiddleware)
    return stack


def test_413_envelope_has_detail_and_request_id_header():
    client = TestClient(_stack_app())
    response = client.post("/echo", content=b"x" * 4096)

    assert response.status_code == 413
    payload = response.json()
    assert "transport limit" in payload["detail"]
    assert "PAPI_MAX_BATCH_UPLOAD_MB" in payload["detail"]
    assert response.headers.get("X-Request-ID")


def test_lying_chunked_client_gets_413():
    """An iterator body goes out chunked (no Content-Length) — counter fires."""
    client = TestClient(_stack_app())
    response = client.post("/echo", content=iter([b"x" * 4096]))

    assert response.status_code == 413
    assert "detail" in response.json()


def test_under_cap_request_reaches_endpoint():
    client = TestClient(_stack_app())
    response = client.post("/echo", content=b"x" * 16)

    assert response.status_code == 200
    assert response.json() == {"received": 16}


# --------------------------------------------------------------------------
# Real app wiring
# --------------------------------------------------------------------------


def test_real_app_middleware_order_keeps_body_cap_innermost():
    """CORS(RequestId(BodyCap(app))): 413s must still carry X-Request-ID."""
    classes = [m.cls.__name__ for m in real_app.user_middleware]
    assert classes.index("RequestSizeLimitMiddleware") > classes.index("RequestIdMiddleware")


def test_real_app_cap_tracks_batch_upload_budget():
    from app.config import get_settings

    settings = get_settings()
    cap = request_body_cap_bytes(settings)
    assert cap == (settings.max_batch_upload_mb + 10) * 1024 * 1024
    registered = next(
        m for m in real_app.user_middleware if m.cls.__name__ == "RequestSizeLimitMiddleware"
    )
    assert registered.kwargs["max_body_bytes"] == cap


def test_413_body_is_valid_json_envelope():
    """The hand-built body must parse as the app-wide {"detail": ...} shape."""
    sent: list = []

    async def inner_app(scope, receive, send):  # pragma: no cover - never called
        raise AssertionError("unreachable")

    middleware = RequestSizeLimitMiddleware(inner_app, max_body_bytes=5)

    async def receive():  # pragma: no cover - never called
        raise AssertionError("unreachable")

    scope = _http_scope(headers=[(b"content-length", b"6")])
    asyncio.run(middleware(scope, receive, _collecting_send(sent)))
    payload = json.loads(sent[1]["body"])
    assert set(payload) == {"detail"}
