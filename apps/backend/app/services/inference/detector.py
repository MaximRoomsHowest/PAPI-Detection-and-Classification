"""Single-frame YOLO detection. Takes the loaded model + runtime knobs as plain
arguments (no service state), so the ``InferenceService._detect_frame`` wrapper
just binds ``self.model`` / ``self.settings.confidence_threshold`` / ``self.device``."""

from typing import Any


def detect_frame(
    model: Any,
    frame: Any,
    *,
    use_tracking: bool,
    reset_tracker: bool,
    conf: float,
    device: str,
) -> list[dict]:
    """Run YOLO on a single frame.

    ``use_tracking=True`` routes through Ultralytics' ByteTrack so per-lamp
    identity is maintained across frames inside a video request. The
    ``reset_tracker`` flag controls whether the tracker state from a
    previous video bleeds into this one (audit B-MAJ-1): pass
    ``reset_tracker=True`` on the FIRST frame of every new video and
    ``False`` thereafter. Implementation: Ultralytics treats
    ``persist=False`` as "reinitialise the tracker on this call" and
    ``persist=True`` as "continue with whatever state the predictor has".
    Reversing the previous always-False default re-enables ByteTrack's
    actual job (continuity) while keeping cross-request isolation.
    """
    if use_tracking:
        results = model.track(
            frame,
            persist=not reset_tracker,
            tracker="bytetrack.yaml",
            conf=conf,
            device=device,
            verbose=False,
        )
    else:
        results = model.predict(
            frame,
            conf=conf,
            device=device,
            verbose=False,
        )

    if not results:
        return []

    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return []

    detections: list[dict] = []
    for box in boxes:
        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0]]
        detections.append(
            {
                "class_id": int(box.cls[0]),
                "confidence": round(float(box.conf[0]), 4),
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                # ByteTrack id on the video/tracking path; None for single-image predict.
                "track_id": int(box.id[0]) if getattr(box, "id", None) is not None else None,
            }
        )
    return detections
