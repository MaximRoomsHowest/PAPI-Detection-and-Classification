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

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings
from app.services.inference import get_inference_service

__all__ = [
    "router",
    "require_api_key",
    "get_settings",
    "get_inference_service",
]


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    settings = get_settings()
    # Constant-time comparison so a timing side-channel can't recover the key
    # character-by-character (audit IMP-BE-9 / IMP-SEC-1).
    if settings.api_key and not (x_api_key and hmac.compare_digest(x_api_key, settings.api_key)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# The sub-routers are imported AFTER require_api_key / the seams are bound above
# (they reference ``routes.require_api_key`` at decoration time). Each carries
# the same ``/api`` prefix; including them here yields one combined router with
# every original path, method, response_model and auth dependency intact.
from app.api.routers import (  # noqa: E402 - must follow the definitions above
    analyze_router,
    logs_router,
    meta_router,
    stats_router,
)

router = APIRouter()
router.include_router(analyze_router)
router.include_router(logs_router)
router.include_router(stats_router)
router.include_router(meta_router)
