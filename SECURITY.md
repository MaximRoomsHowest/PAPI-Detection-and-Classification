# Security

PAPI Lights Detection and Classification is a demonstrator built for Intersoft
Electronics Services BV. It is not a public service, but the backend is hardened
so it can be deployed safely.

## Reporting a vulnerability

Contact the repository owner directly or open a private security advisory on
GitHub. Please do not file public issues for security problems.

## Security posture

- The API has provider-based operator auth. Production refuses to start if auth
  resolves to open access and still rejects the default database credentials.
  Supported providers are first-party local email/password sessions, the legacy
  constant-time `X-API-Key` check, optional Supabase Auth bearer-token
  validation, and an advanced `local_supabase` mode for deliberate fallback
  deployments.
- Supabase support is optional and uses the public anon key only. Operator
  authorization is based on `app_metadata` roles or an explicit email allowlist;
  user-controlled `user_metadata` is not trusted.
- Uploaded media is validated by type and size; annotated artifacts are served
  from a path-traversal-guarded route behind the same operator-auth gate.
- Process-local rate limiting is enabled by default, with stricter buckets for
  `/api/auth/login` credential attempts and expensive `/api/analyze*`
  inference requests, plus `Retry-After` on 429s.
- Drone metadata (latitude / longitude / altitude) is range-validated before it
  reaches the geometry math.
- Postgres is bound to loopback in the bundled `compose.yaml`, the backend API
  port binds to loopback by default, and the containers run as non-root users
  (with all Linux capabilities dropped) with log rotation enabled.
- See `docs/architecture-overview.md` for the full request flow.

## Dependency scanning

CI runs `pip-audit` against the backend requirements and `npm audit
--audit-level=high` against the frontend on every push (see the `security` job
in `.github/workflows/ci.yml`). The steps are advisory today and are flipped to
blocking before final hand-off, once the initial findings are triaged.

## Known gaps (tracked, not yet implemented)

Secret scanning, credential rotation policy, and a formal threat model are
tracked improvements in the project audit notes.

## Third-party licensing

The project is licensed proprietary to Intersoft Electronics Services BV (see
[`LICENSE`](LICENSE)). The detector is built on Ultralytics YOLO, which is
**AGPL-3.0**: any distribution or hosted use of the trained weights must comply
with AGPL-3.0 or be covered by a separate commercial Ultralytics license. Resolve
that obligation before any external distribution or hosted offering.
