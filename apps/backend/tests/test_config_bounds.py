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
