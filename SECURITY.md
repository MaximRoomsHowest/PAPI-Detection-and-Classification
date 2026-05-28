# Security

PAPI Detection & Classification is an academic industry-project demo built for
Intersoft Electronics. It is not a public service, but the backend is hardened so
it can be deployed safely.

## Reporting a vulnerability

Contact the repository owner directly or open a private security advisory on
GitHub. Please do not file public issues for security problems.

## Security posture

- The API requires an `X-API-Key` header when `PAPI_ENV=production`; the backend
  refuses to start in production without one and rejects the default database
  credentials. The key is compared in constant time.
- Uploaded media is validated by type and size; annotated artifacts are served
  from a path-traversal-guarded route behind the same API key.
- Drone metadata (latitude / longitude / altitude) is range-validated before it
  reaches the geometry math.
- Postgres is bound to loopback in the bundled `docker-compose.yml`, and the
  containers run as a non-root user with log rotation enabled.
- See `docs/architecture-overview.md` for the full request flow.

## Known gaps (tracked, not yet implemented)

Rate limiting, dependency-vulnerability scanning in CI, secret scanning, and a
formal threat model are tracked improvements in the project audit notes.

## Third-party licensing

The detector is built on Ultralytics YOLO, which is **AGPL-3.0**. Any distribution
or hosted use of the trained weights must respect that license; confirm the
intended licensing of this repository with Intersoft before handover.
