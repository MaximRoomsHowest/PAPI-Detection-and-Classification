"""Startup orchestration for the FastAPI backend.

Keeping this module separate from ``app.main`` keeps the ASGI entry point focused
on routing and middleware. Startup has several operational responsibilities
(schema init, registry/dataset seeding, orphan reconciliation, storage readiness,
thread limits, and inference warmup), so it deserves one explicit home.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import Settings
from app.database import init_db
from app.runtime_threads import (
    apply_runtime_threads,
    install_ort_thread_limit,
    install_ov_thread_limit,
)
from app.services.auth import validate_auth_startup
from app.services.inference import get_inference_service
from app.services.storage import get_media_storage

logger = logging.getLogger(__name__)

# Substring used to detect the default development DB credentials in
# settings.database_url. Anything else (including a non-default user at the same
# host) passes the production startup gate.
DEFAULT_DB_CREDENTIAL_MARKER = "papi:papi@"


def validate_production_startup(settings: Settings) -> None:
    """Fail fast on production deployments that are still using local defaults."""
    if settings.environment.lower() != "production":
        return

    validate_auth_startup(settings)
    if DEFAULT_DB_CREDENTIAL_MARKER in settings.database_url:
        raise RuntimeError(
            "PAPI_DATABASE_URL still uses the default 'papi:papi' credentials. "
            "Set a real PAPI_DATABASE_URL before starting in production mode."
        )


def _seed_model_registry(settings: Settings) -> None:
    """Copy the frozen models.json registry into the DB table on first boot.

    Idempotent: it never clobbers operator edits. Failures are logged, never
    fatal, because the inference service can fall back to the frozen JSON
    registry when the table is empty.
    """
    try:
        from app.database import get_sessionmaker
        from app.repositories.model_registry import ModelRegistryRepository
        from app.services.model_registry import load_model_registry

        session = get_sessionmaker()()
        try:
            repo = ModelRegistryRepository(session)
            frozen = load_model_registry(settings)
            seeded = repo.seed_from_frozen(frozen)
            reconciled = repo.reconcile_builtins_from_frozen(frozen)
            if seeded:
                logger.info("Seeded %d built-in model(s) into the registry table.", seeded)
            if reconciled:
                logger.info("Reconciled %d built-in model registry row(s).", reconciled)
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 - seeding must never abort startup
        logger.warning("Model registry seeding skipped: %s", exc)


def _seed_datasets(settings: Settings) -> None:
    """Seed built-in evaluation datasets and register project datasets."""
    try:
        from app.database import get_sessionmaker
        from app.services.datasets_seed import seed_builtin_datasets, seed_project_datasets

        session = get_sessionmaker()()
        try:
            seeded = seed_builtin_datasets(settings, session)
            if seeded:
                logger.info("Seeded %d built-in evaluation dataset(s).", seeded)
            registered = seed_project_datasets(settings, session)
            if registered:
                logger.info("Registered %d project dataset(s).", registered)
        finally:
            session.close()
    except Exception as exc:  # noqa: BLE001 - seeding must never abort startup
        logger.warning("Dataset seeding skipped: %s", exc)


def _reconcile_orphaned_jobs() -> None:
    """Mark jobs left ``running`` by a previous process as failed."""
    try:
        from app.services.jobs import get_job_runner

        reconciled = get_job_runner().reconcile_orphans()
        if reconciled:
            logger.info("Reconciled %d orphaned job(s) to failed after restart.", reconciled)
    except Exception as exc:  # noqa: BLE001 - reconciliation must never abort startup
        logger.warning("Job reconciliation skipped: %s", exc)


def _reap_job_scratch(settings: Settings) -> None:
    """Remove stale background-job scratch so job/storage volumes stay bounded."""
    try:
        from app.services.jobs.cleanup import reap_job_scratch

        removed = reap_job_scratch(settings)
        if removed:
            logger.info("Reaped %d stale job-scratch item(s) at startup.", removed)
    except Exception as exc:  # noqa: BLE001 - cleanup must never abort startup
        logger.warning("Job-scratch reaping skipped: %s", exc)


def _ensure_storage_ready(settings: Settings) -> None:
    """Fail startup when Azure Blob storage is configured but unreachable."""
    if settings.storage_backend == "azure_blob":
        get_media_storage(settings).ensure_ready()


def _prewarm_inference() -> None:
    """Best-effort detector load, smoke test, and optional model preload."""
    try:
        service = get_inference_service()
        _ = service.model
        service.warmup()
        logger.info("YOLO model pre-warmed and smoke-tested at startup.")
        preloaded = service.preload_available_models()
        if preloaded:
            logger.info("Registry models loaded at startup: %s", ", ".join(preloaded))
    except RuntimeError as exc:
        logger.warning("Could not pre-warm YOLO model: %s", exc)
    except Exception as exc:  # noqa: BLE001 - warmup is best-effort; never abort startup
        logger.warning("YOLO warmup inference failed: %s", exc)


def run_startup_tasks(settings: Settings, inference_threads: int) -> None:
    """Blocking startup work, intended to run off the event loop."""
    init_db()
    _seed_model_registry(settings)
    _seed_datasets(settings)
    _reconcile_orphaned_jobs()
    _reap_job_scratch(settings)
    _ensure_storage_ready(settings)

    # Pin runtime thread pools now, just before torch/cv2/onnxruntime are loaded.
    apply_runtime_threads(inference_threads)
    install_ort_thread_limit(inference_threads)
    install_ov_thread_limit(inference_threads)
    _prewarm_inference()


async def shutdown_runtime_services() -> None:
    """Best-effort graceful shutdown for process-local workers."""
    try:
        from app.services.jobs import get_job_runner

        await asyncio.get_running_loop().run_in_executor(
            None, lambda: get_job_runner().shutdown(wait=True)
        )
    except Exception:  # noqa: BLE001 - shutdown drain is best-effort
        logger.warning("JobRunner shutdown drain failed.", exc_info=True)
