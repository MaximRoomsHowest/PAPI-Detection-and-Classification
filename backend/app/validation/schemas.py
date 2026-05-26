from typing import Literal

from pydantic import BaseModel, Field


LampState = Literal["white", "red", "transition", "unknown"]
MediaType = Literal["image", "video"]


class BoundingBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class LampResult(BaseModel):
    index: int
    state: LampState
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox | None = None


class AnglePerLight(BaseModel):
    runway_lamp: int
    distance_m: float
    elevation_angle_deg: float


class AngleResult(BaseModel):
    angle_available: bool
    elevation_angle_deg: float | None = None
    per_light_angles: list[AnglePerLight] = Field(default_factory=list)
    angle_source: str | None = None
    angle_note: str


class AnalysisPayload(BaseModel):
    log_id: str | None = None
    media_type: MediaType
    original_filename: str
    runway_id: str
    drone_id: str | None = None
    global_state: str
    lamps: list[LampResult]
    confidence: float
    frame_width: int | None = None
    frame_height: int | None = None
    frame_count: int
    processing_ms: int
    angle: AngleResult
    artifact_url: str | None = None
    detections: list[dict] = Field(default_factory=list)


class FrameBatchPayload(BaseModel):
    frame_count: int
    processing_ms: int
    results: list[AnalysisPayload]


class LogListItem(BaseModel):
    id: str
    media_type: MediaType
    runway_id: str
    drone_id: str | None
    original_filename: str
    global_state: str
    confidence: float
    angle_available: bool
    elevation_angle_deg: float | None
    frame_count: int
    processing_ms: int
    artifact_url: str | None = None
    created_at: str


class RunwayLight(BaseModel):
    point: int
    latitude: float
    longitude: float
    altitude_m: float


class RunwayResponse(BaseModel):
    id: str
    label: str
    lights: list[RunwayLight]
