"""Background-job request/response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    """A background job's durable state, polled by the frontend."""

    id: str
    kind: str  # evaluate | label_assist | train_prepare
    status: str  # queued | running | succeeded | failed | cancelled
    phase: str | None = None
    progress: float = 0.0
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
