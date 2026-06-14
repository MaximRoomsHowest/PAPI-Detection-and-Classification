"""Single-frame YOLO detection. Takes the loaded model + runtime knobs as plain
arguments (no service state), so the ``InferenceService._detect_frame`` wrapper
just binds ``self.model`` / ``self.settings.confidence_threshold`` / ``self.device``."""

from typing import Any


def lamp_redness(frame: Any, x1: int, y1: int, x2: int, y2: int) -> float | None:
    """Measured "redness" of a lamp crop: the red-channel fraction (R/(R+G+B)),
    scaled to 0-255 and averaged over the inner 60% of the bbox.

    High while the lamp is red, low once it turns white (a white lamp has R~G~B, so
    its red fraction drops to ~1/3). This is the real pixel measurement behind the
    client's "Redness vs angle" graph — NOT derived from the classified state. The
    inner-60% crop avoids the dark halo around the lamp. Returns None when the frame
    isn't an image array or the crop is empty, so callers stay None-safe.
    """
    if not hasattr(frame, "shape") or getattr(frame, "ndim", 0) < 3:
        return None
    try:
        h, w = frame.shape[:2]
        x1c, x2c = max(0, x1), min(w, x2)
        y1c, y2c = max(0, y1), min(h, y2)
        if x2c <= x1c or y2c <= y1c:
            return None
        bw, bh = x2c - x1c, y2c - y1c
        ix1, ix2 = x1c + int(bw * 0.2), x2c - int(bw * 0.2)
        iy1, iy2 = y1c + int(bh * 0.2), y2c - int(bh * 0.2)
        if ix2 <= ix1 or iy2 <= iy1:
            ix1, iy1, ix2, iy2 = x1c, y1c, x2c, y2c
        crop = frame[iy1:iy2, ix1:ix2]
        if crop.size == 0:
            return None
        # cv2 frames are BGR: channel 0=B, 1=G, 2=R.
        blue = float(crop[:, :, 0].mean())
        green = float(crop[:, :, 1].mean())
        red = float(crop[:, :, 2].mean())
        total = red + green + blue
        if total <= 0:
            return None
        return round(255.0 * red / total, 1)
    except Exception:  # noqa: BLE001 - redness is a best-effort display metric; any error -> None
        return None


def detect_frame(
    model: Any,
    frame: Any,
    *,
    use_tracking: bool,
    reset_tracker: bool,
    conf: float,
    device: str,
    imgsz: int = 1280,
    iou: float = 0.7,
    max_det: int = 4,
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
            iou=iou,
            imgsz=imgsz,
            device=device,
            max_det=max_det,
            verbose=False,
        )
    else:
        results = model.predict(
            frame,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device=device,
            max_det=max_det,
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
                # Real measured redness of the lamp crop (drives the Redness-vs-angle chart).
                "redness": lamp_redness(frame, x1, y1, x2, y2),
            }
        )
    return detections
