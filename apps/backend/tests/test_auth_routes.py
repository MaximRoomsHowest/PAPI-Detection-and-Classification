from __future__ import annotations

import pytest
from app.config import Settings
from app.main import app
from app.services.auth import hash_password
from fastapi.testclient import TestClient


def _settings(**overrides):
    values = {
        "database_url": "sqlite:///:memory:",
        "storage_dir": ".test-storage",
        "auth_mode": "open",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client():
    return TestClient(app)


def _route_settings(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr("app.api.routes.get_settings", lambda: settings)


def test_auth_config_reports_enabled_provider_flags(client, monkeypatch: pytest.MonkeyPatch):
    _route_settings(
        monkeypatch,
        _settings(
            auth_mode="local_supabase",
            api_key="break-glass",
            auth_session_secret="dev-secret",
            local_admin_email="admin@example.com",
            local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
            supabase_anon_key="anon",
            supabase_allowed_emails=["operator@example.com"],
        ),
    )

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "local_supabase",
        "password_login_enabled": True,
        "api_key_enabled": True,
        "supabase_enabled": True,
    }


def test_local_login_returns_session_and_me_accepts_bearer(client, monkeypatch: pytest.MonkeyPatch):
    _route_settings(
        monkeypatch,
        _settings(
            auth_mode="local",
            auth_session_secret="dev-secret",
            local_admin_email="admin@example.com",
            local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        ),
    )

    login = client.post(
        "/api/auth/login",
        json={"email": "ADMIN@example.com", "password": "s3cret"},
    )

    assert login.status_code == 200
    body = login.json()
    assert body["user"] == {
        "authenticated": True,
        "provider": "local",
        "email": "admin@example.com",
        "roles": ["admin"],
    }
    assert body["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"


def test_login_returns_generic_401_for_bad_password(client, monkeypatch: pytest.MonkeyPatch):
    _route_settings(
        monkeypatch,
        _settings(
            auth_mode="local",
            auth_session_secret="dev-secret",
            local_admin_email="admin@example.com",
            local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        ),
    )

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_login_returns_400_when_password_provider_disabled(client, monkeypatch: pytest.MonkeyPatch):
    _route_settings(monkeypatch, _settings(auth_mode="api_key", api_key="legacy-secret"))

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "s3cret"},
    )

    assert response.status_code == 400
    assert "Password login is not enabled" in response.json()["detail"]


def test_me_accepts_api_key_break_glass_in_supabase_mode(client, monkeypatch: pytest.MonkeyPatch):
    _route_settings(
        monkeypatch,
        _settings(
            auth_mode="supabase",
            api_key="break-glass",
            supabase_anon_key="anon",
            supabase_allowed_emails=["operator@example.com"],
        ),
    )

    response = client.get("/api/auth/me", headers={"X-API-Key": "break-glass"})

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "provider": "api_key",
        "email": None,
        "roles": ["admin"],
    }


def test_me_returns_anonymous_shape_for_invalid_credentials(client, monkeypatch: pytest.MonkeyPatch):
    _route_settings(monkeypatch, _settings(auth_mode="api_key", api_key="expected"))

    response = client.get("/api/auth/me", headers={"X-API-Key": "wrong"})

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "provider": None,
        "email": None,
        "roles": [],
    }
