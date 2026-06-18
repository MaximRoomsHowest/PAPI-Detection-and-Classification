"""Shared job-runner contracts.

Handlers import this module instead of ``jobs.runner`` so the runner can register
handlers without creating a bidirectional import. Keep this file lightweight:
only stable contracts that both the runner and handlers need belong here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.config import Settings
from app.repositories.jobs import JobRepository


class JobCancelled(Exception):
    """Raised by a handler when it observes a cooperative cancel request."""


class JobContext:
    """The handle a handler uses to report progress and observe cancellation.

    Wraps a ``JobRepository`` bound to the worker's own session. Handlers should
    call ``check_cancelled()`` at natural checkpoints so a cancel request takes
    effect promptly.
    """

    def __init__(self, job_id: str, settings: Settings, repo: JobRepository):
        self.job_id = job_id
        self.settings = settings
        self._repo = repo

    def progress(self, phase: str | None = None, fraction: float | None = None) -> None:
        self._repo.set_progress(self.job_id, phase, fraction)

    def cancelled(self) -> bool:
        return self._repo.is_cancel_requested(self.job_id)

    def check_cancelled(self) -> None:
        if self.cancelled():
            raise JobCancelled()


JobHandler = Callable[[dict[str, Any], JobContext], dict[str, Any] | None]
