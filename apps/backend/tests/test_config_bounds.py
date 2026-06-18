"""Settings field-bound coverage (app.config.Settings).

test_config.py already pins confidence_threshold and the CORS parsing. This
file adds the sequence_fps bounds and the max_video_seconds=0 sentinel, which
are load-bearing:

  * sequence_fps drives annotated-playback speed / transition timing; it is
    constrained ``gt=0, le=120`` so a 0 or absurd env value can't break the
    folder->video pipeline.
  * max_video_seconds keeps a SUPPORTED 0 sentinel ("no duration cap"), so its
    lower bound is ``ge=0`` not ``gt=0`` — a regression to gt=0 would refuse to
    boot a perfectly valid config.

Bounds are exercised via the real env path (monkeypatch.setenv) so the
EnvSettingsSource + validator wiring is covered, matching the style of the
existing env-driven config tests.
"""

from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import ValidationError


def test_sequence_fps_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_SEQUENCE_FPS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_sequence_fps_above_max_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_SEQUENCE_FPS", "121")
    with pytest.raises(ValidationError):
        Settings()


def test_sequence_fps_within_range_accepted(monkeypatch):
    monkeypatch.setenv("PAPI_SEQUENCE_FPS", "10")
    assert Settings().sequence_fps == 10.0


def test_sequence_fps_upper_boundary_accepted(monkeypatch):
    monkeypatch.setenv("PAPI_SEQUENCE_FPS", "120")
    assert Settings().sequence_fps == 120.0


def test_max_video_seconds_zero_sentinel_loads(monkeypatch):
    """0 means "no duration cap" and MUST remain a valid value (ge=0)."""
    monkeypatch.setenv("PAPI_MAX_VIDEO_SECONDS", "0")
    settings = Settings()
    assert settings.max_video_seconds == 0


def test_max_video_seconds_negative_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_MAX_VIDEO_SECONDS", "-1")
    with pytest.raises(ValidationError):
        Settings()


def test_max_batch_upload_mb_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_MAX_BATCH_UPLOAD_MB", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_max_batch_upload_mb_default_matches_proxy_budget(monkeypatch):
    monkeypatch.delenv("PAPI_MAX_BATCH_UPLOAD_MB", raising=False)
    # Default folder/batch budget; the frontend nginx cap (PAPI_NGINX_MAX_BODY_SIZE,
    # default 2048m) and the backend transport cap (budget + 10 MB) must stay above it.
    assert Settings().max_batch_upload_mb == 2000


def test_max_image_megapixels_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_MAX_IMAGE_MEGAPIXELS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_max_image_megapixels_default(monkeypatch):
    monkeypatch.delenv("PAPI_MAX_IMAGE_MEGAPIXELS", raising=False)
    assert Settings().max_image_megapixels == 80


def test_db_pool_size_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_DB_POOL_SIZE", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_db_max_overflow_negative_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_DB_MAX_OVERFLOW", "-1")
    with pytest.raises(ValidationError):
        Settings()


def test_db_max_overflow_zero_accepted(monkeypatch):
    """0 overflow (a strictly fixed-size pool) is a valid operator choice."""
    monkeypatch.setenv("PAPI_DB_MAX_OVERFLOW", "0")
    assert Settings().db_max_overflow == 0


def test_db_pool_defaults(monkeypatch):
    monkeypatch.delenv("PAPI_DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("PAPI_DB_MAX_OVERFLOW", raising=False)
    settings = Settings()
    assert settings.db_pool_size == 10
    assert settings.db_max_overflow == 20


def test_db_pool_env_override(monkeypatch):
    monkeypatch.setenv("PAPI_DB_POOL_SIZE", "25")
    monkeypatch.setenv("PAPI_DB_MAX_OVERFLOW", "50")
    settings = Settings()
    assert settings.db_pool_size == 25
    assert settings.db_max_overflow == 50


def test_rate_limit_defaults(monkeypatch):
    monkeypatch.delenv("PAPI_RATE_LIMIT_ENABLED", raising=False)
    monkeypatch.delenv("PAPI_RATE_LIMIT_PER_MINUTE", raising=False)
    monkeypatch.delenv("PAPI_AUTH_RATE_LIMIT_PER_MINUTE", raising=False)
    monkeypatch.delenv("PAPI_ANALYZE_RATE_LIMIT_PER_MINUTE", raising=False)
    settings = Settings()
    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_per_minute == 600
    assert settings.auth_rate_limit_per_minute == 20
    assert settings.analyze_rate_limit_per_minute == 60


def test_rate_limit_can_be_disabled(monkeypatch):
    monkeypatch.setenv("PAPI_RATE_LIMIT_ENABLED", "false")
    assert Settings().rate_limit_enabled is False


def test_rate_limit_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_RATE_LIMIT_PER_MINUTE", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_analyze_rate_limit_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_ANALYZE_RATE_LIMIT_PER_MINUTE", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_auth_rate_limit_zero_rejected(monkeypatch):
    monkeypatch.setenv("PAPI_AUTH_RATE_LIMIT_PER_MINUTE", "0")
    with pytest.raises(ValidationError):
        Settings()
