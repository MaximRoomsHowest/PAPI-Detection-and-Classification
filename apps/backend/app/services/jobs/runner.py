"""Single-worker background-job runner.

The backend has no task queue and serialises inference on one re-entrant lock.
Long-running work (evaluation, assisted labeling) runs here instead, on a
``ThreadPoolExecutor(max_workers=1)`` so jobs run strictly serially — never two
YOLO loads competing for RAM. Durable state lives in the ``jobs`` table, so the
frontend polls progress and a restart reconciles orphans.

Isolation rules that matter:
* The worker thread opens its OWN SQLAlchemy session (never a request session).
* Handlers construct their OWN ``YOLO`` instance from a weights path and do NOT
  acquire the inference lock, so the live demo stays responsive — only CPU/RAM is
  shared, which is acceptable and observable via the job phase/progress.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

from app.config import Settings
from app.database import get_sessionmaker
from app.repositories.jobs import TERMINAL_STATUSES, JobRepository
from app.services.jobs.contracts import JobCancelled, JobContext, JobHandler

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="papi-job")
        self._handlers: dict[str, JobHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        # Deferred imports: handler modules pull in ultralytics only inside their
        # bodies, but importing them here keeps the runner import cheap regardless.
        from app.services.jobs.handlers.evaluate import run_evaluate
        from app.services.jobs.handlers.label_assist import run_label_assist

        self._handlers = {
            "evaluate": run_evaluate,
            "label_assist": run_label_assist,
        }

    def register(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    def submit(self, kind: str, params: dict[str, Any]) -> str:
        """Create a durable job row and schedule it on the worker. Returns the id."""
        session = get_sessionmaker()()
        try:
            job = JobRepository(session).create(kind, params)
            job_id = job.id
        finally:
            session.close()
        self._executor.submit(self._run, job_id)
        return job_id

    def _run(self, job_id: str) -> None:
        session = get_sessionmaker()()
        repo = JobRepository(session)
        try:
            job = repo.get(job_id)
            if job is None or job.status in TERMINAL_STATUSES:
                # Cancelled or removed before the worker picked it up.
                return
            handler = self._handlers.get(job.kind)
            if handler is None:
                repo.mark_failed(job_id, f"No handler registered for job kind '{job.kind}'.")
                return
            if repo.mark_running(job_id) == 0:
                # A cancel (or other terminal transition) landed in the window
                # between the status check above and here — the guarded CAS did not
                # apply, so honour the cancel instead of running the job.
                return
            ctx = JobContext(job_id, self._settings, repo)
            params = dict(job.params_json or {})
            result = handler(params, ctx)
            if repo.is_cancel_requested(job_id):
                repo.mark_cancelled(job_id)
            else:
                repo.mark_succeeded(job_id, result if isinstance(result, dict) else None)
        except JobCancelled:
            repo.mark_cancelled(job_id)
        except Exception as exc:  # noqa: BLE001 - any handler failure becomes a failed job
            logger.exception("Job %s (%s) failed.", job_id, kind_of(repo, job_id))
            try:
                repo.mark_failed(job_id, str(exc) or exc.__class__.__name__)
            except Exception:  # noqa: BLE001 - last-ditch; the job stays 'running' otherwise
                logger.exception("Could not mark job %s failed.", job_id)
        finally:
            session.close()

    def reconcile_orphans(self) -> int:
        session = get_sessionmaker()()
        try:
            return JobRepository(session).reconcile_orphans()
        finally:
            session.close()

    def shutdown(self, wait: bool = True) -> None:
        """Drain the worker on app shutdown so an in-flight job can finish and persist
        its terminal state, using the SIGTERM grace window instead of being abandoned
        (which would leave it 'running' until the next startup reconcile)."""
        self._executor.shutdown(wait=wait)


def kind_of(repo: JobRepository, job_id: str) -> str:
    job = repo.get(job_id)
    return job.kind if job else "?"


@lru_cache(maxsize=1)
def get_job_runner() -> JobRunner:
    from app.config import get_settings

    return JobRunner(get_settings())
