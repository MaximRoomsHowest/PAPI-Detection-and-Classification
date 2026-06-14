"""Startup reaper for stale background-job scratch.

Background jobs leave artifacts on the ``jobs`` volume that are never referenced
again once the job is done:
  * training bundles  — ``jobs_dir/<job_id>/bundle.zip`` (a full dataset copy),
  * eval run dirs     — ``jobs_dir/eval/eval-<job_id>/`` (only stray ones survive,
    since the evaluate handler deletes its own run dir on success),
  * crash-orphaned temp upload zips — ``tmp_dir/*.zip`` from a SIGKILL mid-stream.

mtime-based so it needs no DB coupling: a directory/file older than the TTL is
removed. Runs once at startup; safe to call repeatedly.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

# Crash-orphaned temp upload zips are short-lived by design; reap aggressively.
_TMP_ZIP_TTL_SECONDS = 3600


def _older_than(path: Path, now: float, ttl_seconds: float) -> bool:
    try:
        return (now - path.stat().st_mtime) > ttl_seconds
    except OSError:
        return False


def _reap_dirs(parent: Path, now: float, ttl_seconds: float, *, skip: set[str] = frozenset()) -> int:
    if not parent.is_dir():
        return 0
    removed = 0
    for child in parent.iterdir():
        if child.name in skip or not child.is_dir():
            continue
        if _older_than(child, now, ttl_seconds):
            shutil.rmtree(child, ignore_errors=True)
            removed += 1
    return removed


def reap_job_scratch(settings: Settings) -> int:
    """Delete stale job scratch + crash-orphaned temp uploads. Returns count removed."""
    now = time.time()
    ttl = settings.job_scratch_ttl_hours * 3600
    removed = 0
    # Training bundles: jobs_dir/<job_id>/ (skip the shared eval/ subtree, handled below).
    removed += _reap_dirs(settings.jobs_dir, now, ttl, skip={"eval"})
    # Stray eval run dirs (normal ones are deleted by the evaluate handler on success).
    removed += _reap_dirs(settings.jobs_dir / "eval", now, ttl)
    # Crash-orphaned temp upload zips.
    if settings.tmp_dir.is_dir():
        for zip_path in settings.tmp_dir.glob("*.zip"):
            if zip_path.is_file() and _older_than(zip_path, now, _TMP_ZIP_TTL_SECONDS):
                zip_path.unlink(missing_ok=True)
                removed += 1
    return removed
