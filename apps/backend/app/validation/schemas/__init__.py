"""Request/response Pydantic models, split by domain.

Previously one ``schemas.py``; the models now live in cohesive submodules
(``common``, ``lamp``, ``angle``, ``analysis``, ``log``, ``system``, ``runway``).
Everything is re-exported here so ``from app.validation.schemas import X`` keeps
working unchanged for every call site.
"""

from app.validation.schemas.analysis import AnalysisPayload, FrameBatchPayload
from app.validation.schemas.angle import (
    AnglePerLight,
    AngleResult,
    AngleSample,
    FramePoint,
    TransitionEvent,
)
from app.validation.schemas.common import (
    BoundingBox,
    GlobalState,
    LampState,
    MediaType,
)
from app.validation.schemas.datasets import (
    CandidateBox,
    CandidateImage,
    CandidatesResponse,
    CommitBox,
    CommitImage,
    CommitRequest,
    CommitResponse,
    DatasetResponse,
)
from app.validation.schemas.jobs import JobResponse
from app.validation.schemas.lamp import Detection, FrameLampState, LampResult
from app.validation.schemas.log import LogListItem
from app.validation.schemas.runway import (
    RunwayCreate,
    RunwayLight,
    RunwayLightInput,
    RunwayResponse,
)
from app.validation.schemas.system import (
    InferenceStats,
    ModelInfo,
    SystemInfo,
    UploadLimits,
    ValMetrics,
    WeatherMetrics,
)
from app.validation.schemas.training import (
    EvaluateRequest,
    PrepareTrainingRequest,
    PrepareTrainingResponse,
    TrainHyperparams,
)

__all__ = [
    # common
    "LampState",
    "MediaType",
    "GlobalState",
    "BoundingBox",
    # lamp
    "Detection",
    "LampResult",
    "FrameLampState",
    # angle
    "AnglePerLight",
    "AngleResult",
    "TransitionEvent",
    "FramePoint",
    "AngleSample",
    # analysis
    "AnalysisPayload",
    "FrameBatchPayload",
    # log
    "LogListItem",
    # system
    "ValMetrics",
    "WeatherMetrics",
    "ModelInfo",
    "InferenceStats",
    "SystemInfo",
    "UploadLimits",
    # runway
    "RunwayLight",
    "RunwayResponse",
    "RunwayLightInput",
    "RunwayCreate",
    # jobs
    "JobResponse",
    # datasets
    "DatasetResponse",
    "CandidateBox",
    "CandidateImage",
    "CandidatesResponse",
    "CommitBox",
    "CommitImage",
    "CommitRequest",
    "CommitResponse",
    # training
    "TrainHyperparams",
    "PrepareTrainingRequest",
    "PrepareTrainingResponse",
    "EvaluateRequest",
]
