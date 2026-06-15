"""Dataset + assisted-labeling request/response schemas."""

from pydantic import BaseModel, Field


class DatasetResponse(BaseModel):
    id: str
    name: str
    source: str  # bundle | assisted | builtin
    status: str  # ready | labeling | draft
    class_names: dict[int, str] | None = None
    n_train: int = 0
    n_val: int = 0
    n_test: int = 0
    created_at: str | None = None


class CandidateBox(BaseModel):
    """A YOLO-normalized candidate box (centre + size, all in 0..1)."""

    class_id: int = Field(ge=0)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)
    conf: float | None = Field(default=None, ge=0.0, le=1.0)


class CandidateImage(BaseModel):
    image_id: str
    image_url: str | None = None
    width: int | None = None
    height: int | None = None
    boxes: list[CandidateBox] = Field(default_factory=list)


class CandidatesResponse(BaseModel):
    dataset_id: str
    status: str
    total: int
    images: list[CandidateImage] = Field(default_factory=list)


class CommitBox(BaseModel):
    class_id: int = Field(ge=0)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)


class CommitImage(BaseModel):
    image_id: str
    boxes: list[CommitBox] = Field(default_factory=list)
    # Skip an image entirely (e.g. nothing to label / bad frame).
    skip: bool = False


class CommitRequest(BaseModel):
    images: list[CommitImage] = Field(default_factory=list)


class CommitResponse(BaseModel):
    dataset_id: str
    n_committed: int
    status: str
