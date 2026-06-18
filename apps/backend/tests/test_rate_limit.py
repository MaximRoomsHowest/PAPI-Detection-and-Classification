"""Application rate limiting.

The limiter is intentionally small and process-local: it protects the demo
backend from accidental refresh loops or repeated expensive inference requests
without adding Redis or an edge dependency. These tests pin the public contract
instead of the internal deque implementation.
"""

from __future__ import annotations

from app.logging_config import RequestIdMiddleware
from app.main import app as real_app
from app.middleware import RateLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _limited_app(*, enabled: bool = True) -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/analyze-frame")
    def analyze_frame() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/auth/login")
    def login() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(
        RateLimitMiddleware,
        enabled=enabled,
        general_limit_per_minute=2,
        auth_limit_per_minute=1,
        analyze_limit_per_minute=1,
    )
    app.add_middleware(RequestIdMiddleware)
    return app


def test_general_bucket_returns_429_after_limit():
    client = TestClient(_limited_app())

    assert client.get("/ok").status_code == 200
    response = client.get("/ok")
    assert response.status_code == 200
    assert response.headers["X-RateLimit-Remaining"] == "0"

    blocked = client.get("/ok")
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")
    assert blocked.headers.get("X-Request-ID")
    assert "Rate limit exceeded" in blocked.json()["detail"]


def test_analyze_bucket_uses_stricter_limit():
    client = TestClient(_limited_app())

    assert client.post("/api/analyze-frame").status_code == 200
    blocked = client.post("/api/analyze-frame")

    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Limit"] == "1"


def test_auth_login_uses_credential_attempt_bucket():
    client = TestClient(_limited_app())

    assert client.post("/api/auth/login").status_code == 200
    blocked = client.post("/api/auth/login")

    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Limit"] == "1"


def test_health_and_disabled_limiter_do_not_count():
    client = TestClient(_limited_app())
    for _ in range(5):
        assert client.get("/health").status_code == 200
    assert client.get("/ok").status_code == 200

    disabled = TestClient(_limited_app(enabled=False))
    for _ in range(5):
        assert disabled.get("/ok").status_code == 200


def test_stale_client_entries_are_swept(monkeypatch):
    """Clients that never return must not occupy the hit map forever.

    This one deliberately reaches into the limiter internals: the leak is only
    observable in the size of the hit map, not in any HTTP response.
    """
    import app.middleware as middleware

    clock = {"now": 1000.0}
    monkeypatch.setattr(middleware, "monotonic", lambda: clock["now"])
    limiter = RateLimitMiddleware(
        None,
        enabled=True,
        general_limit_per_minute=5,
        auth_limit_per_minute=2,
        analyze_limit_per_minute=1,
    )
    for i in range(50):
        limiter._record_hit(f"10.0.0.{i}", "general", 5)
    assert len(limiter._hits) == 50

    clock["now"] += 121  # every recorded hit expired and the sweep deadline passed
    limiter._record_hit("10.0.0.250", "general", 5)
    assert set(limiter._hits) == {("10.0.0.250", "general")}


def test_real_app_middleware_order_keeps_rate_limit_before_body_read():
    """CORS(RequestId(RateLimit(BodyCap(app))))."""
    classes = [m.cls.__name__ for m in real_app.user_middleware]
    assert classes.index("RateLimitMiddleware") < classes.index("RequestSizeLimitMiddleware")
    assert classes.index("RateLimitMiddleware") > classes.index("RequestIdMiddleware")
