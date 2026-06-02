"""Read-only metadata endpoints: runway list, model info, host/runtime facts.

``/model`` and ``/system`` resolve ``get_inference_service`` / ``get_settings``
through the ``app.api.routes`` module object so the test monkeypatches on that
namespace reach them (see the note in ``routers.analyze``).
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends

import app.api.routes as routes
from app.services.runways import list_runways
from app.validation.schemas import ModelInfo, RunwayResponse, SystemInfo

router = APIRouter(prefix="/api")


@router.get("/runways", response_model=list[RunwayResponse])
def get_runways() -> list[RunwayResponse]:
    return list_runways()


@router.get("/model", response_model=ModelInfo)
def get_model_info(_auth: Annotated[None, Depends(routes.require_api_key)] = None) -> ModelInfo:
    return routes.get_inference_service().model_info()


@router.get("/system", response_model=SystemInfo)
def get_system(_auth: Annotated[None, Depends(routes.require_api_key)] = None) -> SystemInfo:
    """Host + runtime facts (audit IMP-BE-7) — every value read from the running host."""
    import platform as platform_module
    from importlib.metadata import PackageNotFoundError, version

    settings = routes.get_settings()
    torch_available = cuda_available = False
    cuda_device_count = 0
    try:
        import torch

        torch_available = True
        cuda_available = bool(torch.cuda.is_available())
        cuda_device_count = torch.cuda.device_count() if cuda_available else 0
    except Exception:  # noqa: BLE001 - the torch probe is best-effort
        pass

    try:
        app_version = version("papi-detection")
    except PackageNotFoundError:
        app_version = "unknown"

    return SystemInfo(
        platform=platform_module.platform(),
        python_version=platform_module.python_version(),
        cpu_count=os.cpu_count(),
        torch_available=torch_available,
        cuda_available=cuda_available,
        cuda_device_count=cuda_device_count,
        device_configured=settings.device,
        app_version=app_version,
    )
