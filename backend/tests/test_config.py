from app.config import REPO_ROOT, Settings


def test_default_model_path_points_to_repo_models_serving():
    settings = Settings()

    assert settings.model_path == REPO_ROOT / "models" / "serving" / "best.pt"


def test_documented_relative_model_override_resolves_to_repo_models_serving():
    settings = Settings(PAPI_MODEL_PATH="../models/serving/best.pt")

    assert settings.model_path == REPO_ROOT / "models" / "serving" / "best.pt"


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
