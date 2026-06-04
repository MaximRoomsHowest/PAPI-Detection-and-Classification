"""Read-only metadata endpoints: runway list, model info, host/runtime facts.

``/model`` and ``/system`` resolve ``get_inference_service`` / ``get_settings``
through the ``app.api.routes`` module object so the test monkeypatches on that
namespace reach them (see the note in ``routers.analyze``).
"""

from __future__ import annotations

import os
import platform as platform_module
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

import app.api.routes as routes
from app.services.runways import add_runway, delete_runway, list_runways
from app.validation.schemas import ModelInfo, RunwayCreate, RunwayResponse, SystemInfo

router = APIRouter(prefix="/api")


@router.get("/runways", response_model=list[RunwayResponse])
def get_runways(_auth: Annotated[None, Depends(routes.require_api_key)] = None) -> list[RunwayResponse]:
    return list_runways()


@router.post("/runways", response_model=RunwayResponse, status_code=status.HTTP_201_CREATED)
def create_runway(
    payload: RunwayCreate,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> RunwayResponse:
    """Register a runway the model can actually score against.

    The four lamp coordinates feed the same ENU elevation-angle solver and
    ``validate_runway_id`` gate as the built-in runways, so an analysis sent with
    the new ``runway_id`` works end-to-end. Pydantic rejects malformed bodies
    (wrong lamp count, out-of-range coords) as 422; an id collision is 409.
    """
    try:
        runway = add_runway(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RunwayResponse(**runway)


@router.delete("/runways/{runway_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_runway(
    runway_id: str,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> Response:
    """Delete a custom runway. Built-in surveyed runways are protected (400);
    an unknown id is 404."""
    try:
        delete_runway(runway_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown runway_id: {runway_id}") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/model", response_model=ModelInfo)
def get_model_info(_auth: Annotated[None, Depends(routes.require_api_key)] = None) -> ModelInfo:
    return routes.get_inference_service().model_info()


@router.get("/system", response_model=SystemInfo)
def get_system(_auth: Annotated[None, Depends(routes.require_api_key)] = None) -> SystemInfo:
    """Host + runtime facts (audit IMP-BE-7) — every value read from the running host."""
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
