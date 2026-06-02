"""Per-concern API routers, assembled into the single ``/api`` router.

Each submodule owns one slice of the surface:

* ``analyze`` — the upload + inference endpoints (image / batch / sequence)
* ``logs``    — the persisted-analysis list, CSV export, and detail
* ``stats``   — aggregate stats over the whole log table
* ``meta``    — runway list, model info, host/runtime facts

``app.api.routes`` includes all four into its ``router`` and remains the public
import surface (``from app.api.routes import router, require_api_key, ...``).
"""

from app.api.routers.analyze import router as analyze_router
from app.api.routers.logs import router as logs_router
from app.api.routers.meta import router as meta_router
from app.api.routers.stats import router as stats_router

__all__ = ["analyze_router", "logs_router", "meta_router", "stats_router"]
