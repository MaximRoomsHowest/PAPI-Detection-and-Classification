"""Lock-wait observability (InferenceService._acquire_inference_lock).

Inference is serialized on one RLock by design (audit H1), so a request queued
behind a long video analysis can wait minutes with no signal. The contextmanager
logs the wait so ops can tell "queued" from "hung". These tests pin:

  * an uncontended acquire stays silent (no log noise per request),
  * a contended acquire logs the wait once the INFO threshold is crossed,
  * the manager still acquires re-entrantly (the dispatcher pattern).
"""

from __future__ import annotations

import logging
import threading

import app.services.inference.service as service_module
from app.config import Settings
from app.services.inference import InferenceService


def make_service(tmp_path) -> InferenceService:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
    )
    return InferenceService(settings)


def test_uncontended_acquire_logs_nothing(tmp_path, caplog):
    service = make_service(tmp_path)
    with caplog.at_level(logging.INFO, logger=service_module.__name__):
        with service._acquire_inference_lock():
            pass
    assert not [record for record in caplog.records if "lock wait" in record.getMessage().lower()]


def test_contended_acquire_logs_the_wait(tmp_path, caplog, monkeypatch):
    # Any nonzero wait should log: drop the INFO threshold to 0 so the test
    # doesn't depend on real timing.
    monkeypatch.setattr(service_module, "_LOCK_WAIT_INFO_S", 0.0)
    service = make_service(tmp_path)

    held = threading.Event()
    release = threading.Event()

    def hold_lock():
        with service._lock:
            held.set()
            release.wait(timeout=10)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert held.wait(timeout=10)

    # Release the holder shortly after the main thread starts waiting.
    releaser = threading.Timer(0.05, release.set)
    releaser.start()
    try:
        with caplog.at_level(logging.INFO, logger=service_module.__name__):
            with service._acquire_inference_lock():
                pass
    finally:
        release.set()
        holder.join(timeout=10)
        releaser.cancel()

    waits = [record for record in caplog.records if "Inference lock wait" in record.getMessage()]
    assert len(waits) == 1


def test_acquire_is_reentrant(tmp_path):
    service = make_service(tmp_path)
    # The dispatcher holds the lock while nested helpers re-acquire it; the
    # instrumented manager must preserve that (RLock semantics).
    with service._acquire_inference_lock():
        with service._lock:
            assert True
