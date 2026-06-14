"""Regression tests for the backend audit hardening pass.

Covers: the evenly_spaced(cap<=0) guard, the startup job-scratch reaper, and the
app-layer security headers (present even without the nginx proxy).
"""

from __future__ import annotations

import os
import time


def test_evenly_spaced_zero_and_boundaries():
    from app.services.inference.angle_resolver import evenly_spaced

    assert evenly_spaced([1, 2, 3], 0) == []
    assert evenly_spaced([1, 2, 3], 1) == [1]
    assert evenly_spaced([1, 2, 3], 10) == [1, 2, 3]
    assert evenly_spaced([1, 2, 3, 4, 5], 3) == [1, 3, 5]


def test_reap_job_scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPI_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PAPI_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PAPI_JOB_SCRATCH_TTL_HOURS", "168")

    from app.config import Settings
    from app.services.jobs.cleanup import reap_job_scratch

    settings = Settings()
    jobs = settings.jobs_dir
    (jobs / "eval").mkdir(parents=True)
    tmp = settings.tmp_dir
    tmp.mkdir(parents=True)

    old = time.time() - 200 * 3600  # older than the 168h TTL

    old_bundle = jobs / "oldjob"
    old_bundle.mkdir()
    (old_bundle / "bundle.zip").write_bytes(b"x")
    os.utime(old_bundle, (old, old))

    fresh_bundle = jobs / "freshjob"
    fresh_bundle.mkdir()
    (fresh_bundle / "bundle.zip").write_bytes(b"x")

    old_eval = jobs / "eval" / "eval-old"
    old_eval.mkdir()
    os.utime(old_eval, (old, old))

    old_zip = tmp / "old.zip"
    old_zip.write_bytes(b"x")
    os.utime(old_zip, (old, old))
    fresh_zip = tmp / "fresh.zip"
    fresh_zip.write_bytes(b"x")

    removed = reap_job_scratch(settings)

    assert removed == 3
    assert not old_bundle.exists()
    assert fresh_bundle.exists()  # within TTL -> kept
    assert not old_eval.exists()
    assert not old_zip.exists()
    assert fresh_zip.exists()  # within the 1h temp TTL -> kept


def test_security_headers_present_on_direct_access():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
