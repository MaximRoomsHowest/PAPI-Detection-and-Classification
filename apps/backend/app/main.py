"""FastAPI application entry point.

The lifespan context manager replaces the deprecated ``@app.on_event``
decorators and is used to (a) initialise the database schema and
(b) pre-warm the YOLO model so the first inference request after boot
does not pay the ~5 s model-load latency in front of a jury (audit
B-CRIT-4 + SMOKE-MAJ-2).
"""

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
from app.database import get_session, init_db
from app.logging_config import RequestIdMiddleware, configure_logging
from app.middleware import RateLimitMiddleware, RequestSizeLimitMiddleware, request_body_cap_bytes
from app.services.inference import get_inference_service
from app.services.storage import get_media_storage

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


def _allow_cors_credentials(origins: list[str]) -> bool:
    """Never combine wildcard CORS origins with credentialed responses."""
    return not any("*" in origin for origin in origins)


def _startup_warmup() -> None:
    """Blocking startup work, run in a thread so it doesn't stall the event loop.

    ``init_db()`` creates the analysis_logs table; touching ``.model`` triggers the lazy
    YOLO weight load; ``warmup()`` runs one dummy inference so a broken checkpoint fails
    here, not in front of the jury on the first request. All failures are logged, never
    fatal — a missing-weights local dev env can still serve /health and /api/runways.
    """
    init_db()
    # Azure Blob readiness is a hard dependency when configured: an unreachable
    # or misconfigured storage account should abort startup loudly instead of
    # failing on the first artifact write mid-demo. Runs here (worker thread)
    # because the SDK call is blocking network I/O. Local mode is a no-op.
    if settings.storage_backend == "azure_blob":
        get_media_storage(settings).ensure_ready()
    try:
        service = get_inference_service()
        _ = service.model
        service.warmup()
        logger.info("YOLO model pre-warmed and smoke-tested at startup.")
        # Best-effort load of the NON-default registry entries too, so a corrupt
        # optional checkpoint (nano/transition) surfaces here as a log line instead
        # of a mid-demo 503 while the first selecting request holds the inference
        # lock (audit WARM-1). Failures are logged inside preload, never raised.
        preloaded = service.preload_available_models()
        if preloaded:
            logger.info("Registry models loaded at startup: %s", ", ".join(preloaded))
    except RuntimeError as exc:
        logger.warning("Could not pre-warm YOLO model: %s", exc)
    except Exception as exc:  # noqa: BLE001 - warmup is best-effort; never abort startup
        logger.warning("YOLO warmup inference failed: %s", exc)


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
        if not settings.api_key or not settings.api_key.strip():
            raise RuntimeError(
                "PAPI_API_KEY must be set when PAPI_ENV=production. "
                "Refusing to start an unauthenticated public-facing instance."
            )
        if _DEFAULT_DB_CREDENTIAL_MARKER in settings.database_url:
            raise RuntimeError(
                "PAPI_DATABASE_URL still uses the default 'papi:papi' credentials. "
                "Set a real PAPI_DATABASE_URL before starting in production mode."
            )

    # init_db + the lazy YOLO load + warmup are blocking and CPU-bound (~5 s). Run them
    # off the event loop in a thread so the loop stays responsive (signal handling,
    # cancellation) during startup. Note: uvicorn does not accept connections until
    # lifespan startup completes, so no request — /health included — is served before
    # this finishes either way (audit CMT-1; compose HEALTHCHECK start-period covers it).
    await asyncio.get_running_loop().run_in_executor(None, _startup_warmup)
    yield
    # Nothing to clean up on shutdown for now; placeholder for future use.


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
    allow_headers=["Content-Type", "X-API-Key"],
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

app.include_router(router)


@app.get("/media/{file_path:path}")
def get_media(
    file_path: str,
    request: Request,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> Response:
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
