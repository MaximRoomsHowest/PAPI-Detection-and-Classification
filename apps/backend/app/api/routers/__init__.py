"""Per-concern API routers, assembled into the single ``/api`` router.

Each submodule owns one slice of the surface:

* ``analyze``      — the upload + inference endpoints (image / batch / sequence)
* ``auth``         — login/session metadata for the SPA shell
* ``logs``         — the persisted-analysis list, CSV export, and detail
* ``stats``        — aggregate stats over the whole log table
* ``meta``         — runway list, model info, host/runtime facts
* ``models_admin`` — model upload / promote / disable / delete / evaluate
* ``datasets``     — dataset bundle upload + assisted labeling + commit
* ``training``     — external training bundle preparation
* ``jobs``         — background-job status + cancellation

``app.api.routes`` includes them all into its ``router`` and remains the public
import surface (``from app.api.routes import router, require_api_key, ...``).
"""

from app.api.routers.analyze import router as analyze_router
from app.api.routers.auth import router as auth_router
from app.api.routers.datasets import router as datasets_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.logs import router as logs_router
from app.api.routers.meta import router as meta_router
from app.api.routers.models_admin import router as models_admin_router
from app.api.routers.stats import router as stats_router
from app.api.routers.training import router as training_router

__all__ = [
    "analyze_router",
    "auth_router",
    "logs_router",
    "meta_router",
    "stats_router",
    "models_admin_router",
    "datasets_router",
    "training_router",
    "jobs_router",
]
