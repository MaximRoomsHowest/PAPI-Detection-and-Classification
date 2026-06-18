from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Public auth capability metadata for the SPA shell.

    No secrets are included. The frontend uses this to decide whether to render
    an email/password form, an API-key fallback, or the open-local unlock button.
    """

    mode: str
    password_login_enabled: bool
    api_key_enabled: bool
    supabase_enabled: bool


class AuthUser(BaseModel):
    authenticated: bool
    provider: str | None = None
    email: str | None = None
    roles: list[str] = Field(default_factory=list)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    user: AuthUser
