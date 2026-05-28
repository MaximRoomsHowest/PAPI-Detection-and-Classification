"""FastAPI application entry point.

The lifespan context manager replaces the deprecated ``@app.on_event``
decorators and is used to (a) initialise the database schema and
(b) pre-warm the YOLO model so the first inference request after boot
does not pay the ~5 s model-load latency in front of a jury (audit
B-CRIT-4 + SMOKE-MAJ-2).
"""

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import require_api_key, router
from app.config import get_settings
from app.database import init_db
from app.logging_config import RequestIdMiddleware, configure_logging
from app.services.inference import get_inference_service

# Configure structured logging BEFORE any module-level logger is bound
# (audit B-IMP-4). Calling this once at import time means subsequent
# ``logging.getLogger(__name__)`` calls inherit the JSON formatter.
configure_logging(level="INFO")

logger = logging.getLogger(__name__)

settings = get_settings()

# Substring used to detect the default development DB credentials in
# settings.database_url. Anything else (including a non-default user
# at the same host) passes the production startup gate. Kept as a
# module constant so the test can import and reuse it.
_DEFAULT_DB_CREDENTIAL_MARKER = "papi:papi@"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup + shutdown hooks for the FastAPI app.

    Startup:
      * Refuses to boot in production without an API key (audit B-CRIT-5).
      * Refuses to boot in production with the default ``papi:papi``
        database credentials (audit risk follow-up — companion to
        B-CRIT-5).
      * ``init_db()`` creates the analysis_logs table if missing.
      * The YOLO model is touched on the inference service so the
        ultralytics import + weight load happens BEFORE the first
        request arrives. Failures are logged but do not abort startup
        (so a missing-weights local dev environment can still serve
        ``/health`` and ``/api/runways``).
    """
    # B-CRIT-5: hard fail at startup if the operator forgot to set the API key
    # in a real deployment. ``PAPI_ENV=production`` is the explicit opt-in.
    if settings.environment.lower() == "production":
        if not settings.api_key:
            raise RuntimeError(
                "PAPI_API_KEY must be set when PAPI_ENV=production. "
                "Refusing to start an unauthenticated public-facing instance."
            )
        if _DEFAULT_DB_CREDENTIAL_MARKER in settings.database_url:
            raise RuntimeError(
                "PAPI_DATABASE_URL still uses the default 'papi:papi' credentials. "
                "Set a real PAPI_DATABASE_URL before starting in production mode."
            )

    init_db()
    try:
        # Touching .model triggers the lazy YOLO load inside InferenceService.
        # Assigning to `_` makes the side-effect intent explicit (ruff B018).
        _ = get_inference_service().model
        logger.info("YOLO model pre-warmed at startup.")
    except RuntimeError as exc:
        logger.warning("Could not pre-warm YOLO model: %s", exc)
    yield
    # Nothing to clean up on shutdown for now; placeholder for future use.


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# RequestIdMiddleware is added BEFORE CORS so the request-ID context is set
# even for OPTIONS preflight responses. Starlette applies middlewares in
# reverse-insertion order — the last one added is the outermost wrap.
app.add_middleware(RequestIdMiddleware)

# allow_methods / allow_headers are explicit rather than "*" because the
# combination of "*" + allow_credentials=True is rejected by some browsers
# (audit B-MIN-1).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
    expose_headers=["X-Request-ID"],
)

app.include_router(router)


@app.get("/media/{file_path:path}")
def get_media(
    file_path: str,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> FileResponse:
    """Serve annotated artifacts from the exports directory.

    Replaces the previous public ``app.mount("/media", StaticFiles(...))``
    so uploaded analysis artifacts are not retrievable without the same
    API key the inference endpoints already require. When
    ``PAPI_API_KEY`` is unset (local dev mode) ``require_api_key`` is a
    no-op, so /media behaves like the old public mount and no demo
    flow regresses.

    Frontend implication: in a production deployment with an API key,
    the existing ``<img src=/media/...>`` pattern will 401 because the
    browser cannot send the ``X-API-Key`` header on a plain ``<img>``
    request. The frontend must switch to ``fetch`` + ``URL.createObjectURL``
    for media display when an API key is configured — tracked as a
    follow-up to this commit.
    """
    target = (settings.exports_dir / file_path).resolve()
    # Path-traversal guard. The resolve()d target must live under the
    # exports_dir root; anything else (../../etc/passwd, symlinks
    # pointing outside) gets a 404 — never a 403, so the existence of
    # the gate is not itself an information leak.
    try:
        target.relative_to(settings.exports_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
