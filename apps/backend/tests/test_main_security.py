"""Security regression tests for ``app.main``.

Covers the two startup-gate behaviours that defend the deployed
backend from operator footguns:

* /media used to be a public StaticFiles mount; it now requires the
  same API-key dependency as the analyze routes and path-traverses
  to 404 cleanly. These tests pin both behaviours so a future
  refactor that swaps the route handler for a static mount fails
  loudly.
* Production mode refuses to boot with default ``papi:papi`` DB
  credentials, mirroring the existing PAPI_API_KEY check (audit
  B-CRIT-5 follow-up).

These tests are kept separate from ``test_integration.py`` because
they monkeypatch the module-level ``settings`` and clear
``get_settings.cache``, which would interfere with the heavier
integration fixture if they ran in the same module.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app import main as main_module
from app.config import get_settings
from app.main import _DEFAULT_DB_CREDENTIAL_MARKER, app, lifespan
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _route_settings_to_module_singleton(monkeypatch: pytest.MonkeyPatch):
    """Make every ``get_settings()`` call resolve to ``main_module.settings``.

    The route layer (``require_api_key``) calls the lru-cached
    ``get_settings()`` at request time. When tests monkeypatch
    ``main_module.settings.api_key`` they don't otherwise affect the
    cached instance the route would build from env vars, so the
    monkeypatch silently doesn't take. Re-routing ``get_settings`` to
    return the module-level singleton fixes the indirection without
    forcing every test to fight env-var precedence.
    """
    get_settings.cache_clear()
    monkeypatch.setattr("app.config.get_settings", lambda: main_module.settings)
    monkeypatch.setattr("app.api.routes.get_settings", lambda: main_module.settings)
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# /media auth + path traversal
# ---------------------------------------------------------------------------


def _seed_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, filename: str = "annotated.jpg") -> Path:
    """Point the backend's exports dir at a tmp folder and put one file in it.

    ``exports_dir`` is a ``@property`` derived from ``storage_dir`` (see
    ``app.config.Settings``), so we monkeypatch the underlying field and
    let the property recompute. The actual file goes into
    ``storage_dir/exports/`` to match where the property points.

    Returns the file path. The caller can use ``filename`` to navigate
    via the /media route.
    """
    monkeypatch.setattr(main_module.settings, "storage_dir", tmp_path, raising=True)
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    target = exports_dir / filename
    target.write_bytes(b"jpeg-bytes-placeholder")
    return target


@pytest.fixture
def client():
    """A TestClient that does NOT fire lifespan startup events.

    The /media route only reads a file and checks the API key — it never
    touches the database. Using ``TestClient(app)`` WITHOUT the ``with``
    context manager deliberately skips ``lifespan`` (and thus
    ``init_db()``), so these tests run in CI with no Postgres available.
    This mirrors the proven pattern in test_integration.py.
    """
    return TestClient(app)


def test_media_returns_artifact_in_local_mode_without_api_key(client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """No PAPI_API_KEY configured ⇒ /media serves the file (back-compat with
    the previous public StaticFiles mount in local dev / docker compose)."""
    monkeypatch.setattr(main_module.settings, "api_key", None, raising=True)
    _seed_export(monkeypatch, tmp_path)

    response = client.get("/media/annotated.jpg")

    assert response.status_code == 200
    assert response.content == b"jpeg-bytes-placeholder"


def test_media_rejects_request_without_api_key_when_key_is_configured(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """With PAPI_API_KEY set, /media demands the same X-API-Key header
    the analyze routes already require — closing the audit gap."""
    monkeypatch.setattr(main_module.settings, "api_key", "test-secret", raising=True)
    _seed_export(monkeypatch, tmp_path)

    response = client.get("/media/annotated.jpg")

    assert response.status_code == 401


def test_media_serves_artifact_when_correct_api_key_is_supplied(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(main_module.settings, "api_key", "test-secret", raising=True)
    _seed_export(monkeypatch, tmp_path)

    response = client.get("/media/annotated.jpg", headers={"X-API-Key": "test-secret"})

    assert response.status_code == 200
    assert response.content == b"jpeg-bytes-placeholder"


def test_media_404s_on_path_traversal_attempt(client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A request crafted to escape exports_dir must 404, never 200 or 403.

    A 403 here would leak the existence of files outside the export
    root; a 200 is the actual vulnerability. Both must be impossible.
    """
    monkeypatch.setattr(main_module.settings, "api_key", None, raising=True)
    monkeypatch.setattr(main_module.settings, "storage_dir", tmp_path, raising=True)
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
    # Drop a file OUTSIDE the exports_dir that an attacker would target.
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")

    # FastAPI normalises some path segments before routing, so the
    # path-traversal guard lives inside the route handler (resolve()
    # then relative_to() check). All variants must 404.
    for evil in ("subdir/../../secret.txt", "..%2Fsecret.txt"):
        response = client.get(f"/media/{evil}")
        assert response.status_code == 404, f"{evil} unexpectedly returned {response.status_code}"


def test_media_404s_on_missing_file(client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(main_module.settings, "api_key", None, raising=True)
    monkeypatch.setattr(main_module.settings, "storage_dir", tmp_path, raising=True)
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)

    response = client.get("/media/does-not-exist.jpg")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Production-mode default-credential rejection
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_production_lifespan_rejects_default_db_credentials(monkeypatch: pytest.MonkeyPatch):
    """Default papi:papi@ DB URL in production mode ⇒ RuntimeError at
    startup, before the first request can arrive.

    Test the lifespan async context manager directly rather than
    spinning up a TestClient — the TestClient swallows startup
    errors into a 500 on the first request, which is harder to
    assert against precisely.
    """
    monkeypatch.setattr(main_module.settings, "environment", "production", raising=True)
    monkeypatch.setattr(main_module.settings, "api_key", "real-secret", raising=True)
    monkeypatch.setattr(
        main_module.settings,
        "database_url",
        "postgresql+psycopg://papi:papi@localhost:5434/papi_backend",
        raising=True,
    )

    with pytest.raises(RuntimeError, match="papi:papi"):
        async with lifespan(app):
            pass


@pytest.mark.anyio
async def test_production_lifespan_accepts_non_default_db_credentials(monkeypatch: pytest.MonkeyPatch):
    """A custom DB URL is fine — only the literal default credentials
    are blocked. Pin the negation so a future "be even stricter"
    refactor doesn't accidentally reject legitimate URLs."""
    monkeypatch.setattr(main_module.settings, "environment", "production", raising=True)
    monkeypatch.setattr(main_module.settings, "api_key", "real-secret", raising=True)
    monkeypatch.setattr(
        main_module.settings,
        "database_url",
        "postgresql+psycopg://operator:strong-pw@db.internal:5432/papi",
        raising=True,
    )
    # Stub init_db + the YOLO pre-warm so the lifespan body doesn't
    # try to hit a real DB or load a real model.
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(
        main_module,
        "get_inference_service",
        lambda: type("S", (), {"model": None})(),
    )

    async with lifespan(app):
        pass  # no exception ⇒ pass


@pytest.mark.anyio
async def test_production_lifespan_still_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch):
    """Regression for the original B-CRIT-5 check: prove it still
    fires when only the credential gate was added."""
    monkeypatch.setattr(main_module.settings, "environment", "production", raising=True)
    monkeypatch.setattr(main_module.settings, "api_key", None, raising=True)

    with pytest.raises(RuntimeError, match="PAPI_API_KEY"):
        async with lifespan(app):
            pass


def test_default_credential_marker_matches_documented_default():
    """If someone changes the default DB URL in config.py, this test
    will catch the drift between marker and actual default."""
    from app.config import Settings

    default_url = Settings.model_fields["database_url"].default
    assert _DEFAULT_DB_CREDENTIAL_MARKER in default_url, (
        f"Default DB URL '{default_url}' no longer contains the marker "
        f"'{_DEFAULT_DB_CREDENTIAL_MARKER}' the production check looks for. "
        "Update the marker or the default URL so the production check still fires."
    )


# pytest-anyio requires a backend declaration. Use the asyncio backend
# (already a transitive dep via httpx in the backend test suite).
@pytest.fixture
def anyio_backend():
    return "asyncio"
