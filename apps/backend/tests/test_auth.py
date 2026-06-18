from __future__ import annotations

import json

import pytest
from app.config import Settings
from app.services import auth as auth_service
from app.services.auth import (
    AuthError,
    authenticate_request,
    hash_password,
    login_with_password,
    optional_principal,
    validate_auth_startup,
    verify_password,
    verify_session_token,
)


def _settings(**overrides):
    values = {
        "database_url": "sqlite:///:memory:",
        "storage_dir": ".test-storage",
        "auth_mode": "open",
    }
    values.update(overrides)
    return Settings(**values)


def test_password_hash_round_trips_and_rejects_wrong_password():
    encoded = hash_password("correct horse battery staple", salt=b"1234567890abcdef")

    assert verify_password("correct horse battery staple", encoded) is True
    assert verify_password("wrong", encoded) is False
    assert verify_password("correct horse battery staple", "not-a-valid-hash") is False


def test_local_password_login_issues_verifiable_session():
    settings = _settings(
        auth_mode="local",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
    )

    session = login_with_password(settings, email="ADMIN@example.com", password="s3cret")

    assert session.user.email == "admin@example.com"
    assert session.user.provider == "local"
    principal = verify_session_token(settings, session.access_token)
    assert principal.email == "admin@example.com"
    assert principal.has_role("admin")


def test_local_password_login_rejects_wrong_password():
    settings = _settings(
        auth_mode="local",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
    )

    with pytest.raises(AuthError):
        login_with_password(settings, email="admin@example.com", password="wrong")


def test_local_supabase_password_login_accepts_local_admin():
    settings = _settings(
        auth_mode="local_supabase",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        supabase_anon_key="anon",
    )

    session = login_with_password(settings, email="admin@example.com", password="s3cret")

    assert session.user.provider == "local"
    assert session.user.email == "admin@example.com"


def test_local_supabase_password_login_falls_back_to_supabase(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        auth_mode="local_supabase",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        supabase_anon_key="anon",
    )

    def fake_supabase_login(_settings, *, email: str, password: str):
        assert email == "operator@example.com"
        assert password == "supabase-password"
        return auth_service.IssuedSession(
            access_token="supabase-token",
            expires_at=123,
            user=auth_service.Principal(
                subject="user-1",
                provider="supabase",
                email=email,
                roles=("admin",),
            ),
        )

    monkeypatch.setattr(auth_service, "_login_supabase", fake_supabase_login)

    session = login_with_password(
        settings,
        email="operator@example.com",
        password="supabase-password",
    )

    assert session.user.provider == "supabase"


def test_local_supabase_bearer_auth_accepts_local_session():
    settings = _settings(
        auth_mode="local_supabase",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        supabase_anon_key="anon",
    )
    session = auth_service.issue_local_session(settings, email="admin@example.com")

    principal = authenticate_request(
        settings,
        authorization=f"Bearer {session.access_token}",
        x_api_key=None,
    )

    assert principal.provider == "local"
    assert principal.has_role("admin")


def test_local_session_rejects_malformed_base64_token():
    settings = _settings(auth_mode="local", auth_session_secret="dev-secret")

    with pytest.raises(AuthError):
        verify_session_token(settings, "header.not-base64-????.signature")


def test_local_session_rejects_tampered_payload():
    settings = _settings(auth_mode="local", auth_session_secret="dev-secret")
    session = auth_service.issue_local_session(settings, email="admin@example.com")
    header, payload, signature = session.access_token.split(".")
    tampered = auth_service._b64json(
        {
            "sub": "local-admin",
            "email": "attacker@example.com",
            "provider": "local",
            "roles": ["admin"],
            "iat": 1,
            "exp": 9_999_999_999,
        }
    )

    with pytest.raises(AuthError):
        verify_session_token(settings, f"{header}.{tampered}.{signature}")


def test_local_session_rejects_expired_token(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        auth_mode="local",
        auth_session_secret="dev-secret",
        auth_session_ttl_minutes=5,
    )
    monkeypatch.setattr(auth_service.time, "time", lambda: 1_000)
    session = auth_service.issue_local_session(settings, email="admin@example.com")
    monkeypatch.setattr(auth_service.time, "time", lambda: 1_000 + (6 * 60))

    with pytest.raises(AuthError, match="expired"):
        verify_session_token(settings, session.access_token)


def test_optional_principal_returns_none_for_bad_credentials():
    settings = _settings(auth_mode="api_key", api_key="expected")

    assert optional_principal(settings, authorization=None, x_api_key="wrong") is None


def test_api_key_provider_remains_backwards_compatible():
    settings = _settings(auth_mode="api_key", api_key="legacy-secret")

    principal = authenticate_request(settings, authorization=None, x_api_key="legacy-secret")

    assert principal.provider == "api_key"
    assert principal.has_role("admin")


def test_api_key_is_operator_fallback_even_in_supabase_mode():
    settings = _settings(auth_mode="supabase", api_key="break-glass")

    principal = authenticate_request(settings, authorization=None, x_api_key="break-glass")

    assert principal.provider == "api_key"


def test_local_supabase_bearer_auth_falls_back_to_supabase(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        auth_mode="local_supabase",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        supabase_anon_key="anon",
    )

    def fake_supabase_token(_settings, token: str):
        assert token == "supabase-jwt"
        return auth_service.Principal(
            subject="user-1",
            provider="supabase",
            email="operator@example.com",
            roles=("admin",),
        )

    monkeypatch.setattr(auth_service, "authenticate_supabase_token", fake_supabase_token)

    principal = authenticate_request(
        settings,
        authorization="Bearer supabase-jwt",
        x_api_key=None,
    )

    assert principal.provider == "supabase"
    assert principal.email == "operator@example.com"


def test_supabase_token_validation_uses_auth_user_endpoint(monkeypatch: pytest.MonkeyPatch):
    settings = _settings(
        auth_mode="supabase",
        supabase_url="https://project.supabase.co",
        supabase_anon_key="anon-key",
        supabase_allowed_emails=["operator@example.com"],
    )
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "id": "user-1",
                    "email": "operator@example.com",
                    "app_metadata": {},
                    "user_metadata": {"roles": ["admin"]},
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        captured["apikey"] = request.get_header("apikey") or request.get_header("Apikey")
        captured["authorization"] = request.get_header("Authorization")
        return FakeResponse()

    monkeypatch.setattr(auth_service, "urlopen", fake_urlopen)

    principal = auth_service.authenticate_supabase_token(settings, "user-jwt")

    assert captured == {
        "url": "https://project.supabase.co/auth/v1/user",
        "method": "GET",
        "timeout": 10,
        "apikey": "anon-key",
        "authorization": "Bearer user-jwt",
    }
    assert principal.provider == "supabase"
    assert principal.email == "operator@example.com"


def test_supabase_authorization_uses_app_metadata_not_user_metadata():
    settings = _settings(
        auth_mode="supabase",
        supabase_anon_key="anon",
        supabase_required_role="admin",
    )
    user = {
        "id": "user-1",
        "email": "operator@example.com",
        "app_metadata": {},
        "user_metadata": {"roles": ["admin"]},
    }

    with pytest.raises(AuthError):
        auth_service._principal_from_supabase_user(settings, user)


def test_supabase_allowed_email_grants_admin_principal():
    settings = _settings(
        auth_mode="supabase",
        supabase_anon_key="anon",
        supabase_allowed_emails=["operator@example.com"],
    )
    user = {"id": "user-1", "email": "operator@example.com", "app_metadata": {}}

    principal = auth_service._principal_from_supabase_user(settings, user)

    assert principal.provider == "supabase"
    assert principal.has_role("admin")


def test_supabase_app_metadata_admin_grants_operator_principal():
    settings = _settings(auth_mode="supabase", supabase_anon_key="anon")
    user = {
        "id": "user-1",
        "email": "operator@example.com",
        "app_metadata": {"roles": ["Admin"]},
    }

    principal = auth_service._principal_from_supabase_user(settings, user)

    assert principal.provider == "supabase"
    assert principal.roles == ("admin",)


def test_supabase_required_custom_role_grants_operator_principal():
    settings = _settings(
        auth_mode="supabase",
        supabase_anon_key="anon",
        supabase_required_role="papi_operator",
    )
    user = {
        "id": "user-1",
        "email": "operator@example.com",
        "app_metadata": {"roles": ["papi_operator"]},
    }

    principal = auth_service._principal_from_supabase_user(settings, user)

    assert principal.provider == "supabase"
    assert principal.has_role("admin")
    assert principal.has_role("papi_operator")


def test_supabase_authenticated_user_without_operator_role_is_rejected():
    settings = _settings(auth_mode="supabase", supabase_anon_key="anon")
    user = {
        "id": "user-1",
        "email": "operator@example.com",
        "app_metadata": {"roles": ["authenticated"]},
    }

    with pytest.raises(AuthError):
        auth_service._principal_from_supabase_user(settings, user)


def test_production_auto_mode_refuses_open_auth():
    settings = _settings(environment="production", auth_mode="auto", api_key=None)

    with pytest.raises(RuntimeError, match="PAPI_API_KEY"):
        validate_auth_startup(settings)


def test_production_supabase_requires_role_or_allowlist():
    settings = _settings(
        environment="production",
        auth_mode="supabase",
        supabase_anon_key="anon",
        supabase_allowed_emails=[],
        supabase_required_role=None,
    )

    with pytest.raises(RuntimeError, match="PAPI_SUPABASE_ALLOWED_EMAILS"):
        validate_auth_startup(settings)


def test_production_local_supabase_requires_supabase_config():
    settings = _settings(
        environment="production",
        auth_mode="local_supabase",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        supabase_anon_key=None,
    )

    with pytest.raises(RuntimeError, match="PAPI_SUPABASE_ANON_KEY"):
        validate_auth_startup(settings)


def test_production_local_supabase_accepts_both_provider_configs():
    settings = _settings(
        environment="production",
        auth_mode="local_supabase",
        auth_session_secret="dev-secret",
        local_admin_email="admin@example.com",
        local_admin_password_hash=hash_password("s3cret", salt=b"abcdef1234567890"),
        supabase_anon_key="anon",
        supabase_allowed_emails=["operator@example.com"],
    )

    validate_auth_startup(settings)
