# Authentication Setup

The app now has a small provider-based auth layer. The frontend always talks to
the FastAPI backend; Supabase is an optional backend adapter, not a required
runtime dependency for the project.

## Installation Choice

For a client installing the app on a local machine, choose one auth provider in
`.env` before starting Docker Compose:

- **Local login**: simplest setup, one admin email/password stored by the backend
  as a password hash.
- **Supabase login**: users are managed in Supabase Auth, while the app remains
  independent from Supabase SDKs.

Do not configure both for a normal local install. The app still supports
`local_supabase` for a deliberate fallback deployment, but the handoff path is
to pick `local` or `supabase`.

## Modes

`PAPI_AUTH_MODE` controls the provider:

| Mode | Use for | Required values |
|---|---|---|
| `auto` | Backwards-compatible local/demo default | `PAPI_API_KEY` optional |
| `open` | Offline local demos only | None |
| `api_key` | Existing static-key deployments | `PAPI_API_KEY` |
| `local` | Simple first-party operator login | `PAPI_AUTH_SESSION_SECRET`, `PAPI_LOCAL_ADMIN_EMAIL`, `PAPI_LOCAL_ADMIN_PASSWORD_HASH` |
| `supabase` | Optional Supabase Auth login | `PAPI_SUPABASE_URL`, `PAPI_SUPABASE_ANON_KEY`, plus an allowlist or role |
| `local_supabase` | Advanced fallback mode when both login paths must be active | All `local` and `supabase` values |

In production (`PAPI_ENV=production`) the backend refuses to start if auth would
resolve to `open`. Production Supabase mode also requires either
`PAPI_SUPABASE_ALLOWED_EMAILS` or `PAPI_SUPABASE_REQUIRED_ROLE`.

## Option A: Local Email/Password

Use this when the client wants the simplest real user login without adding an
external identity provider.

1. Generate a session signing secret:

   ```powershell
   py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

2. Generate an admin password hash from the backend app directory:

   ```powershell
   cd apps/backend
   ..\..\.venv\Scripts\python.exe -c "from app.services.auth import hash_password; print(hash_password('replace-this-password'))"
   ```

3. Put the values in `.env`:

   ```dotenv
   PAPI_ENV=production
   PAPI_AUTH_MODE=local
   PAPI_AUTH_SESSION_SECRET=<generated-session-secret>
   PAPI_LOCAL_ADMIN_EMAIL=admin@example.com
   PAPI_LOCAL_ADMIN_PASSWORD_HASH=<generated-password-hash>
   ```

`PAPI_API_KEY` may still be set as a break-glass fallback. Requests with that key
continue to work through the legacy `X-API-Key` header.

### Local demo account

For a local handover demo that should still show the real login page, the
installer may use this demo-only account:

| Field | Value |
|---|---|
| Email | `demo.admin@papi.local` |
| Password | `PapiDemo!2026` |

Matching `.env` values:

```dotenv
PAPI_ENV=local
PAPI_AUTH_MODE=local
PAPI_AUTH_SESSION_SECRET=local-demo-session-secret-change-before-sharing
PAPI_LOCAL_ADMIN_EMAIL=demo.admin@papi.local
PAPI_LOCAL_ADMIN_PASSWORD_HASH=pbkdf2_sha256$390000$cGFwaS1kZW1vLTIwMjYhIQ$i-Ft1nF-LjkM4Vyq5UPnHQpkk63Yy57snnK7z8DWptI
```

This block is deliberately not a production template. Rotate the email,
password, password hash, and session secret before a real deployment. If the
machine is only being shown offline, `PAPI_AUTH_MODE=open` is simpler and shows
an **Open admin** button instead of a password form.

## Option B: Supabase Auth

Supabase is intentionally optional. No Supabase SDK is installed in the frontend
or backend; the backend validates bearer tokens directly against the Supabase
Auth API using the public anon key.

For your Supabase project, set:

```dotenv
PAPI_AUTH_MODE=supabase
PAPI_SUPABASE_URL=https://your-project-ref.supabase.co
PAPI_SUPABASE_ANON_KEY=<supabase-public-anon-key>
```

Then choose one authorization rule:

```dotenv
# Option A: explicit operators by email
PAPI_SUPABASE_ALLOWED_EMAILS=operator@example.com,second@example.com

# Option B: require a role from user.app_metadata.roles or user.app_metadata.role.
# Any matching required role is treated as operator/admin access by this app.
PAPI_SUPABASE_REQUIRED_ROLE=papi_operator
```

Important security rules:

- Use the Supabase anon key only. Never put a `service_role` key in `.env`,
  Compose, the frontend, or logs.
- Operator roles are read from `app_metadata`, not `user_metadata`. Users can
  often edit their own `user_metadata`, so it must not grant access.
- The frontend does not need `VITE_SUPABASE_*` values. It calls
  `/api/auth/login`, stores the returned bearer token, and sends it to protected
  backend routes.

## Advanced: Both Providers

Use `PAPI_AUTH_MODE=local_supabase` only when both local and Supabase login must
be available from the same deployment. The backend checks local admin
credentials first, then falls back to Supabase password login. Bearer sessions
work the same way: local sessions are verified first, then Supabase tokens.

```dotenv
PAPI_AUTH_MODE=local_supabase
PAPI_AUTH_SESSION_SECRET=<generated-session-secret>
PAPI_LOCAL_ADMIN_EMAIL=admin@example.com
PAPI_LOCAL_ADMIN_PASSWORD_HASH=<generated-password-hash>
PAPI_SUPABASE_URL=https://your-project-ref.supabase.co
PAPI_SUPABASE_ANON_KEY=<supabase-public-anon-key>
PAPI_SUPABASE_REQUIRED_ROLE=papi_operator
```

## Frontend Behavior

The topbar lock control asks `/api/auth/config` which provider is enabled:

- `local`, `supabase`, and `local_supabase` show email/password login.
- `api_key` shows the legacy key prompt.
- `open` shows an **Open admin** button for offline/local demos.

Protected API calls prefer `Authorization: Bearer <token>` when a user session is
present, then fall back to `X-API-Key` when a legacy key is configured.

## Handoff Checklist

- For local-machine handoff, choose `PAPI_AUTH_MODE=local` or
  `PAPI_AUTH_MODE=supabase` in `.env`.
- For local auth, generate a fresh `PAPI_AUTH_SESSION_SECRET` and store only
  `PAPI_LOCAL_ADMIN_PASSWORD_HASH`, never the plaintext password.
- For Supabase auth, set the anon key and either `PAPI_SUPABASE_ALLOWED_EMAILS`
  or `PAPI_SUPABASE_REQUIRED_ROLE`.
- Keep `PAPI_API_KEY` only if the client wants a legacy or break-glass fallback.
- Rotate all credentials before final production use.
