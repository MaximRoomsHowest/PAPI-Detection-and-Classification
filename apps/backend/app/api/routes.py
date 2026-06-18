"""API surface aggregator.

This module is the stable public import point for the HTTP layer:
``from app.api.routes import router, require_api_key`` keeps working, and the
tests patch the inference / settings seams on *this* module
(``app.api.routes.get_inference_service`` and ``app.api.routes.get_settings``).

The endpoints themselves live in ``app.api.routers`` split by concern
(``analyze`` / ``logs`` / ``stats`` / ``meta``). Those submodules resolve the
two patchable callables through this module object at request time, so the
monkeypatches above reach the handlers without any per-test wiring change.

Import ordering note: ``require_api_key`` (used as ``Depends`` default in the
submodules) and the two seams are defined BEFORE the sub-routers are imported,
because ``Depends(routes.require_api_key)`` is evaluated at the submodules'
function-definition time during that import.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.services.auth import AuthConfigError, AuthError, Principal, authenticate_request
from app.services.inference import get_inference_service

__all__ = [
    "router",
    "require_api_key",
    "get_settings",
    "get_inference_service",
]


def require_api_key(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Principal:
    settings = get_settings()
    try:
        return authenticate_request(settings, authorization=authorization, x_api_key=x_api_key)
    except AuthConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# The sub-routers are imported AFTER require_api_key / the seams are bound above
# (they reference ``routes.require_api_key`` at decoration time). Each carries
# the same ``/api`` prefix; including them here yields one combined router with
# every original path, method, response_model and auth dependency intact.
from app.api.routers import (  # noqa: E402 - must follow the definitions above
    analyze_router,
    auth_router,
    datasets_router,
    jobs_router,
    logs_router,
    meta_router,
    models_admin_router,
    stats_router,
    training_router,
)

router = APIRouter()
router.include_router(auth_router)
router.include_router(analyze_router)
router.include_router(logs_router)
router.include_router(stats_router)
router.include_router(meta_router)
# Model-lifecycle routers (upload / evaluate / datasets / training / jobs). Every
# endpoint they carry is operator-auth gated via Depends(require_api_key).
router.include_router(models_admin_router)
router.include_router(datasets_router)
router.include_router(training_router)
router.include_router(jobs_router)
