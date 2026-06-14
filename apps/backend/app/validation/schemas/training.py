"""Training-launcher + evaluation request/response schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TrainHyperparams(BaseModel):
    """The few knobs the existing trainer exposes. Colour-safe augmentation
    (hsv_h=0, hsv_s=0) is enforced by the launchers, not chosen here, because
    hue/saturation jitter would swap red<->white<->transition labels."""

    epochs: int = Field(default=80, ge=1, le=1000)
    imgsz: int = Field(default=1280, ge=320, le=4096)
    batch: int = Field(default=4, ge=1, le=128)
    oversample: int = Field(default=4, ge=1, le=50)


class PrepareTrainingRequest(BaseModel):
    dataset_id: str
    # Registry id of the base weights to fine-tune from; None -> the bundled yolo26s base.
    base_model_id: str | None = None
    name: str | None = None
    hyperparams: TrainHyperparams = Field(default_factory=TrainHyperparams)


class PrepareTrainingResponse(BaseModel):
    job_id: str
    bundle_url: str | None = None
    command: str
    manifest: dict[str, Any]


class EvaluateRequest(BaseModel):
    dataset_id: str
    # Restrict to held-out splits: evaluating on "train" would write overfitting-inflated
    # metrics back to the model card. An invalid value now yields a clean 422.
    split: Literal["test", "val"] = "test"
