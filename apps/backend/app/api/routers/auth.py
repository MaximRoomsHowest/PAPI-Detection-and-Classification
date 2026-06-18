"""User authentication endpoints for the SPA shell."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status

import app.api.routes as routes
from app.services.auth import (
    AuthConfigError,
    AuthError,
    Principal,
    login_with_password,
    optional_principal,
    password_login_enabled,
    resolved_auth_mode,
)
from app.validation.schemas import AuthConfig, AuthUser, LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth")


def _auth_user(principal: Principal | None) -> AuthUser:
    if principal is None:
        return AuthUser(authenticated=False)
    return AuthUser(
        authenticated=True,
        provider=principal.provider,
        email=principal.email,
        roles=list(principal.roles),
    )


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    settings = routes.get_settings()
    mode = resolved_auth_mode(settings)
    return AuthConfig(
        mode=mode,
        password_login_enabled=password_login_enabled(settings),
        api_key_enabled=bool(settings.api_key and settings.api_key.strip()),
        supabase_enabled=mode in {"supabase", "local_supabase"},
    )


@router.get("/me", response_model=AuthUser)
def current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> AuthUser:
    settings = routes.get_settings()
    return _auth_user(
        optional_principal(settings, authorization=authorization, x_api_key=x_api_key)
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    settings = routes.get_settings()
    try:
        session = login_with_password(settings, email=payload.email, password=payload.password)
    except AuthConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc
    return LoginResponse(
        access_token=session.access_token,
        expires_at=session.expires_at,
        user=_auth_user(session.user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    """Stateless logout endpoint.

    Local sessions and Supabase access tokens are bearer credentials, so server
    logout is a client-side discard for now. Supabase deployments that need
    global revocation can add provider-specific session revocation later without
    changing the frontend contract.
    """

    return Response(status_code=status.HTTP_204_NO_CONTENT)
