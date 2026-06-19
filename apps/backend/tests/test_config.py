import pytest
from app.config import REPO_ROOT, Settings


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ("local", False),
        ("dev", False),
        ("development", False),
        ("test", False),
        ("testing", False),
        ("ci", False),
        ("LOCAL", False),
        (" local ", False),
        ("production", True),
        ("PRODUCTION", True),
        # The whole point of the fix: an unrecognised / typo'd / empty env is treated as
        # production-like so the security floor FAILS CLOSED rather than silently off.
        ("prod", True),
        ("staging", True),
        ("live", True),
        ("", True),
    ],
)
def test_is_production_like_fails_closed_on_unknown_env(env, expected):
    assert Settings(environment=env).is_production_like is expected


def test_default_model_path_points_to_repo_models_serving():
    settings = Settings()

    assert settings.model_path == REPO_ROOT / "models" / "serving" / "best.pt"
    assert settings.model_registry_path == REPO_ROOT / "models" / "serving" / "models.json"


def test_documented_relative_model_override_resolves_to_repo_models_serving():
    settings = Settings(PAPI_MODEL_PATH="../../models/serving/best.pt")

    assert settings.model_path == REPO_ROOT / "models" / "serving" / "best.pt"


def test_documented_onnx_model_override_resolves_to_repo_models_serving():
    settings = Settings(PAPI_MODEL_PATH="../../models/serving/best_int8.onnx")

    assert settings.model_path == REPO_ROOT / "models" / "serving" / "best_int8.onnx"


def test_cors_origins_accept_comma_separated_env_value():
    settings = Settings(PAPI_CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173")

    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_origins_accept_json_style_env_value():
    settings = Settings(PAPI_CORS_ORIGINS='["http://localhost:5173","http://127.0.0.1:5173"]')

    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_default_cors_origins_include_common_vite_dev_ports():
    settings = Settings()

    assert "http://127.0.0.1:5173" in settings.cors_origins
    assert "http://127.0.0.1:5174" in settings.cors_origins


def test_cors_origins_csv_from_env_does_not_crash_settings(monkeypatch):
    """Regression for audit SMOKE-CRIT-2.

    Direct ``Settings(...)`` construction goes through the field validator,
    but production reads from ``EnvSettingsSource`` which used to JSON-decode
    list fields before validators ran -> the comma-separated Compose
    env value crashed the backend container at startup. ``NoDecode`` on
    ``cors_origins`` fixes this; this test pins it.
    """
    monkeypatch.setenv("PAPI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    settings = Settings()

    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_cors_origins_json_from_env_still_works(monkeypatch):
    """JSON-style env vars must continue to work after the NoDecode change."""
    monkeypatch.setenv("PAPI_CORS_ORIGINS", '["http://localhost:5173","http://127.0.0.1:5173"]')
    settings = Settings()

    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_confidence_threshold_rejects_out_of_range_value():
    """Defensive: bad env value should fail validation, not silently pass everything."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(PAPI_CONFIDENCE_THRESHOLD=4.0)


def test_inference_threads_default_is_auto_zero():
    assert Settings().inference_threads == 0


def test_inference_threads_rejects_out_of_range_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(PAPI_INFERENCE_THREADS=-1)
    with pytest.raises(ValidationError):
        Settings(PAPI_INFERENCE_THREADS=1000)


def test_inference_backend_defaults_to_auto():
    assert Settings().inference_backend == "auto"


def test_inference_backend_normalizes_case_and_whitespace():
    assert Settings(PAPI_INFERENCE_BACKEND="  ONNX ").inference_backend == "onnx"


def test_inference_backend_rejects_unknown_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(PAPI_INFERENCE_BACKEND="tensorrt")


def test_environment_defaults_to_local():
    """Production-mode security checks must not fire by default (audit B-CRIT-5)."""
    settings = Settings()
    assert settings.environment.lower() == "local"


def test_environment_can_be_set_to_production_via_env(monkeypatch):
    monkeypatch.setenv("PAPI_ENV", "production")
    settings = Settings()
    assert settings.environment.lower() == "production"


def test_database_url_honors_papi_prefixed_env_var(monkeypatch):
    """PAPI_DATABASE_URL — the convention every other setting uses and the name the
    production startup error references — must be honored via the real env path, not
    silently ignored (audit backend-tests)."""
    monkeypatch.setenv("PAPI_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/papi_x")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/papi_x"


def test_database_url_honors_unprefixed_env_var(monkeypatch):
    """DATABASE_URL (used by Compose and .env.example) must keep working."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/papi_y")
    settings = Settings()
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/papi_y"


def test_empty_transition_model_path_means_not_installed(monkeypatch):
    """compose forwards PAPI_TRANSITION_MODEL_PATH with an empty default; the empty
    string must mean None, not Path('.') resolved against the backend root (IS-2)."""
    monkeypatch.setenv("PAPI_TRANSITION_MODEL_PATH", "")
    assert Settings().transition_model_path is None
