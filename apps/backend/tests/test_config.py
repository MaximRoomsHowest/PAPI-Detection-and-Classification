from app.config import REPO_ROOT, Settings


def test_default_model_path_points_to_repo_models_serving():
    settings = Settings()

    assert settings.model_path == REPO_ROOT / "models" / "serving" / "best.pt"


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
    list fields before validators ran -> the comma-separated docker-compose
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


def test_environment_defaults_to_local():
    """Production-mode security checks must not fire by default (audit B-CRIT-5)."""
    settings = Settings()
    assert settings.environment.lower() == "local"


def test_environment_can_be_set_to_production_via_env(monkeypatch):
    monkeypatch.setenv("PAPI_ENV", "production")
    settings = Settings()
    assert settings.environment.lower() == "production"
