"""Authentication providers for the PAPI backend.

The first public demo used one static ``X-API-Key`` as both the operator password
and the API credential. This module keeps that key as a backwards-compatible
provider, but moves the HTTP layer to a real user/principal boundary:

* ``local`` signs short-lived first-party sessions after an email/password check.
* ``supabase`` validates Supabase Auth bearer tokens against the configured
  Supabase project. It uses the public anon key only; never the service-role key.
* ``local_supabase`` enables both password/session providers in one deployment.
* ``api_key`` preserves the existing deployment flow for simple demos.
* ``open`` is intentionally limited to local/offline use.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings

PASSWORD_HASH_SCHEME = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 390_000


class AuthError(Exception):
    """Raised for bad or missing user credentials."""


class AuthConfigError(Exception):
    """Raised when an enabled provider is missing required configuration."""


@dataclass(frozen=True)
class Principal:
    """Authenticated caller passed through FastAPI dependencies."""

    subject: str
    provider: str
    email: str | None = None
    roles: tuple[str, ...] = ("admin",)

    def has_role(self, role: str) -> bool:
        return role in self.roles


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    expires_at: int
    user: Principal


def resolved_auth_mode(settings: Settings) -> str:
    """Return the effective provider while preserving the old default behavior."""

    mode = settings.auth_mode
    if mode == "auto":
        return "api_key" if _present(settings.api_key) else "open"
    return mode


def password_login_enabled(settings: Settings) -> bool:
    return resolved_auth_mode(settings) in {"local", "supabase", "local_supabase"}


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PASSWORD_HASH_ITERATIONS) -> str:
    """Return a deployable PBKDF2-SHA256 password hash.

    The format is deliberately self-contained so clients can rotate the admin
    password without adding a password-hashing dependency to the production image.
    """

    if not password:
        raise ValueError("password must not be empty")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            PASSWORD_HASH_SCHEME,
            str(iterations),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not password or not encoded:
        return False
    try:
        scheme, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if scheme != PASSWORD_HASH_SCHEME:
            return False
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (binascii.Error, TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def authenticate_request(
    settings: Settings,
    *,
    authorization: str | None,
    x_api_key: str | None,
) -> Principal:
    """Authenticate a protected request and return the current principal."""

    api_key_principal = _authenticate_api_key(settings, x_api_key)
    if api_key_principal:
        return api_key_principal

    mode = resolved_auth_mode(settings)
    if mode == "open":
        return Principal(subject="local-open", provider="open", email=None, roles=("admin",))
    if mode == "api_key":
        raise AuthError("Invalid or missing API key.")

    token = _bearer_token(authorization)
    if not token:
        raise AuthError("Missing bearer token.")
    if mode == "local":
        return verify_session_token(settings, token)
    if mode == "supabase":
        return authenticate_supabase_token(settings, token)
    if mode == "local_supabase":
        return _authenticate_local_or_supabase_token(settings, token)
    raise AuthConfigError(f"Unsupported auth mode: {mode}")


def optional_principal(
    settings: Settings,
    *,
    authorization: str | None,
    x_api_key: str | None,
) -> Principal | None:
    """Best-effort auth for status endpoints such as ``/api/auth/me``."""

    try:
        return authenticate_request(settings, authorization=authorization, x_api_key=x_api_key)
    except AuthError:
        return None


def login_with_password(settings: Settings, *, email: str, password: str) -> IssuedSession:
    mode = resolved_auth_mode(settings)
    if mode == "local":
        return _login_local(settings, email=email, password=password)
    if mode == "supabase":
        return _login_supabase(settings, email=email, password=password)
    if mode == "local_supabase":
        return _login_local_or_supabase(settings, email=email, password=password)
    raise AuthConfigError("Password login is not enabled for this deployment.")


def issue_local_session(settings: Settings, *, email: str, subject: str = "local-admin") -> IssuedSession:
    secret = _required(settings.auth_session_secret, "PAPI_AUTH_SESSION_SECRET")
    expires_at = int(time.time()) + settings.auth_session_ttl_minutes * 60
    roles = ("admin",)
    payload = {
        "sub": subject,
        "email": email,
        "provider": "local",
        "roles": list(roles),
        "iat": int(time.time()),
        "exp": expires_at,
    }
    signing_input = f"{_b64json({'alg': 'HS256', 'typ': 'PAPI'})}.{_b64json(payload)}"
    signature = _b64encode(hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest())
    principal = Principal(subject=subject, provider="local", email=email, roles=roles)
    return IssuedSession(access_token=f"{signing_input}.{signature}", expires_at=expires_at, user=principal)


def verify_session_token(settings: Settings, token: str) -> Principal:
    secret = _required(settings.auth_session_secret, "PAPI_AUTH_SESSION_SECRET")
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
    except ValueError as exc:
        raise AuthError("Invalid session token.") from exc
    signing_input = f"{header_raw}.{payload_raw}"
    expected = _b64encode(hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature_raw, expected):
        raise AuthError("Invalid session token.")
    try:
        payload = json.loads(_b64decode(payload_raw))
    except (binascii.Error, ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Invalid session token.") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("Session expired.")
    if payload.get("provider") != "local":
        raise AuthError("Invalid session token.")
    roles = tuple(str(role) for role in payload.get("roles", []) if role)
    return Principal(
        subject=str(payload.get("sub") or "local-admin"),
        provider="local",
        email=str(payload["email"]) if payload.get("email") else None,
        roles=roles or ("admin",),
    )


def authenticate_supabase_token(settings: Settings, token: str) -> Principal:
    user = _supabase_get_user(settings, token)
    return _principal_from_supabase_user(settings, user)


def validate_auth_startup(settings: Settings) -> None:
    """Fail fast when production auth would be unsafe or unusable."""

    if not settings.is_production_like:
        return

    mode = resolved_auth_mode(settings)
    if mode == "open":
        raise RuntimeError(
            "PAPI_AUTH_MODE resolves to open in production. Set PAPI_API_KEY or choose "
            "PAPI_AUTH_MODE=local or PAPI_AUTH_MODE=supabase."
        )
    if mode == "api_key" and not _present(settings.api_key):
        raise RuntimeError("PAPI_API_KEY must be set when PAPI_AUTH_MODE=api_key in production.")
    if mode in {"local", "local_supabase"}:
        _required_for_startup(settings.auth_session_secret, "PAPI_AUTH_SESSION_SECRET")
        _required_for_startup(settings.local_admin_email, "PAPI_LOCAL_ADMIN_EMAIL")
        _required_for_startup(settings.local_admin_password_hash, "PAPI_LOCAL_ADMIN_PASSWORD_HASH")
    if mode in {"supabase", "local_supabase"}:
        _required_for_startup(settings.supabase_url, "PAPI_SUPABASE_URL")
        _required_for_startup(settings.supabase_anon_key, "PAPI_SUPABASE_ANON_KEY")
        if not settings.supabase_allowed_emails and not _present(settings.supabase_required_role):
            raise RuntimeError(
                "PAPI_AUTH_MODE=supabase in production requires PAPI_SUPABASE_ALLOWED_EMAILS "
                "or PAPI_SUPABASE_REQUIRED_ROLE so any authenticated Supabase user is not "
                "treated as an operator."
            )


def _login_local(settings: Settings, *, email: str, password: str) -> IssuedSession:
    expected_email = _required(settings.local_admin_email, "PAPI_LOCAL_ADMIN_EMAIL").lower()
    expected_hash = _required(settings.local_admin_password_hash, "PAPI_LOCAL_ADMIN_PASSWORD_HASH")
    normalized_email = (email or "").strip().lower()
    if not hmac.compare_digest(normalized_email, expected_email) or not verify_password(password, expected_hash):
        raise AuthError("Invalid email or password.")
    return issue_local_session(settings, email=normalized_email)


def _login_local_or_supabase(settings: Settings, *, email: str, password: str) -> IssuedSession:
    if _local_login_configured(settings):
        try:
            return _login_local(settings, email=email, password=password)
        except AuthError:
            pass
    return _login_supabase(settings, email=email, password=password)


def _login_supabase(settings: Settings, *, email: str, password: str) -> IssuedSession:
    body = _supabase_request_json(
        settings,
        "POST",
        "/auth/v1/token?grant_type=password",
        {"email": email, "password": password},
    )
    token = str(body.get("access_token") or "")
    if not token:
        raise AuthError("Supabase did not return an access token.")
    user = body.get("user") if isinstance(body.get("user"), dict) else _supabase_get_user(settings, token)
    principal = _principal_from_supabase_user(settings, user)
    expires_in = int(body.get("expires_in") or 3600)
    return IssuedSession(access_token=token, expires_at=int(time.time()) + expires_in, user=principal)


def _authenticate_api_key(settings: Settings, x_api_key: str | None) -> Principal | None:
    if not _present(settings.api_key):
        return None
    if x_api_key and hmac.compare_digest(x_api_key, settings.api_key or ""):
        return Principal(subject="api-key-admin", provider="api_key", email=None, roles=("admin",))
    return None


def _authenticate_local_or_supabase_token(settings: Settings, token: str) -> Principal:
    if _local_login_configured(settings):
        try:
            return verify_session_token(settings, token)
        except AuthError:
            pass
    return authenticate_supabase_token(settings, token)


def _local_login_configured(settings: Settings) -> bool:
    return (
        _present(settings.auth_session_secret)
        and _present(settings.local_admin_email)
        and _present(settings.local_admin_password_hash)
    )


def _supabase_get_user(settings: Settings, token: str) -> dict[str, Any]:
    return _supabase_request_json(settings, "GET", "/auth/v1/user", None, bearer_token=token)


def _supabase_request_json(
    settings: Settings,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    base_url = _required(settings.supabase_url, "PAPI_SUPABASE_URL").rstrip("/")
    anon_key = _required(settings.supabase_anon_key, "PAPI_SUPABASE_ANON_KEY")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"apikey": anon_key, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - configured Supabase HTTPS URL
            raw = response.read()
    except HTTPError as exc:
        raise AuthError("Supabase authentication failed.") from exc
    except URLError as exc:
        raise AuthError("Supabase authentication service is unavailable.") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthError("Supabase returned a malformed response.") from exc


def _principal_from_supabase_user(settings: Settings, user: dict[str, Any]) -> Principal:
    subject = str(user.get("id") or "")
    email = str(user.get("email") or "").strip().lower()
    if not subject:
        raise AuthError("Supabase user is missing an id.")
    allowed = {entry.lower() for entry in settings.supabase_allowed_emails}
    allowed_by_email = bool(allowed and email in allowed)
    if allowed and not allowed_by_email:
        raise AuthError("Supabase user is not allowed.")

    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}
    roles = _roles_from_app_metadata(app_metadata)
    required = (settings.supabase_required_role or "").strip().lower()
    required_by_role = bool(required and required in roles)
    if required and not required_by_role:
        raise AuthError("Supabase user is missing the required role.")
    if (allowed_by_email or required_by_role) and "admin" not in roles:
        roles = (*roles, "admin")
    if "admin" not in roles:
        raise AuthError("Supabase user is not an operator.")
    return Principal(
        subject=subject,
        provider="supabase",
        email=email or None,
        roles=roles,
    )


def _roles_from_app_metadata(app_metadata: dict[str, Any]) -> tuple[str, ...]:
    raw_roles = app_metadata.get("roles", app_metadata.get("role", []))
    if isinstance(raw_roles, str):
        role = raw_roles.strip().lower()
        return (role,) if role else ()
    if isinstance(raw_roles, list):
        return tuple(str(role).strip().lower() for role in raw_roles if str(role).strip())
    return ()


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _required(value: str | None, name: str) -> str:
    if not _present(value):
        raise AuthConfigError(f"{name} is required for the selected auth provider.")
    return str(value).strip()


def _required_for_startup(value: str | None, name: str) -> str:
    try:
        return _required(value, name)
    except AuthConfigError as exc:
        raise RuntimeError(str(exc)) from exc


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


def _b64json(value: dict[str, Any]) -> str:
    return _b64encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
