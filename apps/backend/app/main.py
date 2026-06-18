"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import require_api_key, router
from app.config import get_settings
from app.database import get_session
from app.logging_config import RequestIdMiddleware, configure_logging
from app.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    request_body_cap_bytes,
)
from app.runtime_threads import configure_thread_env
from app.services.inference import get_inference_service
from app.services.storage import get_media_storage
from app.startup import (
    DEFAULT_DB_CREDENTIAL_MARKER,
    run_startup_tasks,
    shutdown_runtime_services,
    validate_production_startup,
)

# Configure structured logging BEFORE any module-level logger is bound
# (audit B-IMP-4). Calling this once at import time means subsequent
# ``logging.getLogger(__name__)`` calls inherit the JSON formatter.
configure_logging(level="INFO")

logger = logging.getLogger(__name__)

settings = get_settings()

# Re-exported for the existing startup-gate tests.
_DEFAULT_DB_CREDENTIAL_MARKER = DEFAULT_DB_CREDENTIAL_MARKER

# Bound every CPU thread pool to the container's REAL cpu allotment before torch is ever
# imported (the *_NUM_THREADS env vars are read at import time). Without this, torch/ORT
# spawn one thread per HOST core and thrash inside a fractional-CPU cgroup (e.g. the 2-CPU
# Azure Container Apps replica). Auto-resolves per host (all cores on a dedicated box, the
# cgroup quota in a container), so it is correct on every hardware target. Numerically inert.
# The resolved count is reused at warmup to set the torch/cv2/ORT runtime knobs.
_INFERENCE_THREADS = configure_thread_env(settings.inference_threads)
logger.info(
    "Inference CPU thread budget: %d (PAPI_INFERENCE_THREADS=%s).",
    _INFERENCE_THREADS,
    settings.inference_threads or "auto",
)

def _allow_cors_credentials(origins: list[str]) -> bool:
    """Never combine wildcard CORS origins with credentialed responses."""
    return not any("*" in origin for origin in origins)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup + shutdown hooks for the FastAPI app.

    Startup:
      * Refuses to boot in production without a configured auth provider.
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
    validate_production_startup(settings)

    # init_db + the lazy YOLO load + warmup are blocking and CPU-bound (~5 s). Run them
    # off the event loop in a thread so the loop stays responsive (signal handling,
    # cancellation) during startup. Note: uvicorn does not accept connections until
    # lifespan startup completes, so no request — /health included — is served before
    # this finishes either way (audit CMT-1; compose HEALTHCHECK start-period covers it).
    await asyncio.get_running_loop().run_in_executor(
        None, lambda: run_startup_tasks(settings, _INFERENCE_THREADS)
    )
    yield
    # Drain the background-job worker within the SIGTERM grace window so an in-flight
    # evaluation/labeling job finishes and persists its terminal state, rather than
    # being abandoned and only reconciled to 'failed' on the next startup.
    await shutdown_runtime_services()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# Starlette applies middlewares in reverse-insertion order — the last one
# added is the outermost wrap. Target stack:
# CORS(RequestId(RateLimit(BodyCap(app)))).
#
# The transport body cap is added FIRST (= innermost) so its 413s still flow
# out through RequestIdMiddleware and carry an X-Request-ID. It backstops the
# per-endpoint upload budgets when no nginx sits in front (audit SD-3/CI6).
app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=request_body_cap_bytes(settings))

# Rate limiting sits outside the body cap so repeated expensive analyze calls
# can be rejected before the backend reads the upload body.
app.add_middleware(
    RateLimitMiddleware,
    enabled=settings.rate_limit_enabled,
    general_limit_per_minute=settings.rate_limit_per_minute,
    auth_limit_per_minute=settings.auth_rate_limit_per_minute,
    analyze_limit_per_minute=settings.analyze_rate_limit_per_minute,
)

# RequestIdMiddleware is added BEFORE CORS so the request-ID context is set
# even for OPTIONS preflight responses.
app.add_middleware(RequestIdMiddleware)

# allow_methods / allow_headers are explicit rather than "*" because the
# combination of "*" + allow_credentials=True is rejected by some browsers
# (audit B-MIN-1).
# A "*" origin with allow_credentials=True makes Starlette reflect any Origin AND send
# Access-Control-Allow-Credentials: true — i.e. any-origin-with-credentials. The bare "*"
# (PAPI_CORS_ORIGINS=*) is the case Starlette actually treats as allow-all; we additionally
# drop credentials if ANY entry merely contains "*" (e.g. a wildcard-subdomain that a future
# allow_origin_regex could honour), so the combination can never ship (audit B3).
_cors_allow_credentials = _allow_cors_credentials(settings.cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    # Rate-limit headers exposed so a cross-origin client can see its budget
    # instead of discovering the limiter via a surprise 429.
    expose_headers=[
        "X-Request-ID",
        "X-Total-Count",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
    ],
)

# Added last = outermost wrap, so baseline security headers land on every response
# (incl. CORS/error responses) when the backend is reached directly without the
# nginx proxy that otherwise sets them.
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(router)


@app.get("/media/{file_path:path}")
def get_media(
    file_path: str,
    request: Request,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> Response:
    """Serve annotated artifacts from the exports directory.

    Replaces the previous public ``app.mount("/media", StaticFiles(...))``
    so uploaded analysis artifacts are not retrievable without the same auth
    dependency used by the inference endpoints. In local open mode this still
    behaves like the old public mount, so offline demo flows do not regress.

    Browser media tags cannot send ``Authorization`` or ``X-API-Key`` headers,
    so the frontend resolves protected media through ``fetch`` +
    ``URL.createObjectURL`` before rendering.
    """
    # Path-traversal guard and the explicit content-type allowlist live inside
    # MediaStorage.response_for_media so the local-filesystem and Azure Blob
    # serving paths enforce the exact same rules (out-of-tree -> 404, unknown
    # suffix -> application/octet-stream download). The Range header is passed
    # through because the Azure branch implements byte ranges itself (video
    # seeking needs 206es; FileResponse covers the local branch natively).
    return get_media_storage(settings).response_for_media(
        file_path, range_header=request.headers.get("range")
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(db: Annotated[Session, Depends(get_session)] = None) -> JSONResponse:
    """Deep readiness probe (audit IMP-BE-5).

    Unlike ``/health`` (a pure liveness ping), this checks the dependencies the
    app needs to actually serve a request: the database is reachable and the
    model is loaded in memory. Returns 503 when not ready so a compose healthcheck or
    orchestrator can gate traffic instead of routing to a backend that will 500
    on the first real call.
    """
    checks: dict[str, bool] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001 - any DB error means not-ready
        checks["database"] = False
    # Check the registry default's actual weights, not settings.model_path — with a
    # registry present they can name different files and readiness must track the
    # one the service will really load (audit DEF-1).
    service = get_inference_service()
    checks["model_file_present"] = service.default_weights_present
    checks["model_loaded"] = service.is_loaded

    # A backend whose weights failed to load (broken checkpoint, OOM) is NOT ready:
    # the file existing on disk is necessary but not sufficient to serve a request.
    ready = checks["database"] and checks["model_file_present"] and checks["model_loaded"]
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
