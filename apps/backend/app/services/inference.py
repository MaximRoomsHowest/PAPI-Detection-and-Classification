import os
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.services.angle import compute_elevation_angles, extract_gps_metadata, unavailable_angle
from app.services.model_registry import compute_sha256, load_model_card
from app.services.state import (
    DETECTION_CLASS_TO_STATE,
    confidence_from_lamps,
    detect_lamp_transitions,
    global_state_from_lamps,
    lamp_index_by_track,
    normalize_detections,
)
from app.validation.schemas import AnalysisPayload, AngleResult, LampResult, ModelInfo, ValMetrics


class InferenceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any | None = None
        self._loaded_at: str | None = None
        self._resolved_device: str | None = None
        # A single Ultralytics YOLO instance (with one shared, mutable ByteTrack
        # predictor) is NOT thread-safe. The analyze endpoints are sync `def`s run
        # in FastAPI's threadpool, so concurrent requests would interleave on the
        # shared tracker and scramble the per-lamp identity the verdict/transitions
        # rely on. Serialise all inference (and the lazy model load) on one
        # RE-ENTRANT lock so the dispatcher can also call self.model while holding
        # it. On the single-CPU deployment this matches the ~0.4 fps reality and
        # costs no real throughput (audit H1 / M2 / L1).
        self._lock = threading.RLock()

    def analyze(
        self,
        media_path: Path,
        media_type: str,
        runway_id: str,
        original_filename: str,
        drone_id: str | None = None,
        drone_metadata: tuple[float, float, float] | None = None,
    ) -> AnalysisPayload:
        # Serialise the whole inference so concurrent threadpool requests never
        # share the YOLO/ByteTrack state mid-stream (audit H1).
        with self._lock:
            if media_type == "image":
                return self.analyze_image(media_path, runway_id, original_filename, drone_id, drone_metadata)
            if media_type == "video":
                return self.analyze_video(media_path, runway_id, original_filename, drone_id, drone_metadata)
            raise ValueError(f"Unsupported media type: {media_type}")

    @property
    def is_loaded(self) -> bool:
        """Whether the YOLO weights are loaded in memory (for the readiness probe)."""
        return self._model is not None

    @property
    def device(self) -> str:
        """The device passed to YOLO, expanding ``PAPI_DEVICE=auto`` to cuda when a
        GPU is available else cpu (audit IMP-SRV-2). Cached so torch is probed once;
        an explicit ``cpu``/``cuda``/``0`` setting is used verbatim and never imports torch."""
        if self._resolved_device is None:
            configured = (self.settings.device or "cpu").strip().lower()
            self._resolved_device = self._detect_device() if configured == "auto" else configured
        return self._resolved_device

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:  # noqa: BLE001 - torch import/probe is best-effort
            pass
        return "cpu"

    @staticmethod
    def _open_video_writer(cv2: Any, path: Path, fps: float, width: int, height: int) -> Any | None:
        """Open the annotated-video writer, preferring browser-playable H.264 (avc1)
        and falling back to mp4v when this OpenCV build lacks the H.264 encoder
        (audit IMP-SRV-6). Returns None if neither codec can open a writer."""
        for codec in ("avc1", "mp4v"):
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
            if writer.isOpened():
                return writer
            writer.release()
        return None

    @property
    def model(self) -> Any:
        if self._model is None:
            # Double-checked locking: re-check inside the lock so a concurrent
            # first burst constructs the weights once, not N times (audit L1).
            with self._lock:
                if self._model is None:
                    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
                    try:
                        from ultralytics import YOLO
                    except ImportError as exc:
                        raise RuntimeError("Ultralytics is not installed. Run `pip install -r requirements.txt`.") from exc
                    if not self.settings.model_path.exists():
                        raise RuntimeError(f"Model file not found: {self.settings.model_path}")
                    self._model = YOLO(str(self.settings.model_path))
                    self._loaded_at = datetime.now(timezone.utc).isoformat()
        return self._model

    def model_info(self) -> ModelInfo:
        path = self.settings.model_path
        suffix = path.suffix.lower().lstrip(".") or "unknown"
        backend_type = {
            "onnx": "ultralytics-onnxruntime",
            "pt": "ultralytics-pytorch",
        }.get(suffix, f"ultralytics-{suffix}")
        exists = path.exists()
        file_size_mb = round(path.stat().st_size / (1024 * 1024), 2) if exists else None

        # Provenance comes from models/serving/model_card.json (audit IMP-BE-1).
        # Class names are taken from the live model when loaded (authoritative),
        # otherwise from the card, otherwise None — so the endpoint stays useful
        # whether or not the weights are present.
        card = load_model_card(path) or {}
        classes: dict[int, str] | None = None
        if self._model is not None:
            names = getattr(self._model, "names", None)
            if isinstance(names, dict):
                classes = {int(key): str(value) for key, value in names.items()}
        if classes is None and isinstance(card.get("classes"), dict):
            classes = {int(key): str(value) for key, value in card["classes"].items()}
        val_metrics = card.get("val_metrics")

        return ModelInfo(
            model_path=str(path),
            model_filename=path.name,
            model_format=suffix,
            backend_type=backend_type,
            exists=exists,
            file_size_mb=file_size_mb,
            confidence_threshold=self.settings.confidence_threshold,
            device=self.device,
            loaded=self._model is not None,
            sha256=compute_sha256(path),
            classes=classes,
            model_id=card.get("model_id"),
            training_run=card.get("training_run"),
            base_weights=card.get("base_weights"),
            dataset_split_evaluated=card.get("split_evaluated"),
            val_metrics=ValMetrics(**val_metrics) if isinstance(val_metrics, dict) else None,
            loaded_at=self._loaded_at,
        )

    def warmup(self) -> None:
        """Run one dummy inference so a broken checkpoint surfaces at startup rather
        than on the first real request in front of the jury (audit IMP-SRV-9).
        Best-effort — the caller logs failures and never aborts startup."""
        import numpy as np

        self._detect_frame(np.zeros((64, 64, 3), dtype=np.uint8), use_tracking=False)

    def analyze_image(
        self,
        media_path: Path,
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        drone_metadata: tuple[float, float, float] | None,
    ) -> AnalysisPayload:
        cv2 = self._require_cv2()
        start = perf_counter()
        frame = cv2.imread(str(media_path))
        if frame is None:
            raise ValueError("Could not read uploaded image.")

        detections = self._detect_frame(frame, use_tracking=False)
        # A single image yields red/white per lamp; a "transition" requires a
        # red<->white switch across frames, so there are none here. The angle is
        # still computed for display / transition association.
        angle = self._angle_for_media(media_path, runway_id, drone_metadata)
        lamps = normalize_detections(detections)
        global_state = global_state_from_lamps(lamps)
        confidence = confidence_from_lamps(lamps)

        annotated = self._draw_overlay(frame, lamps, global_state, confidence, angle.elevation_angle_deg)
        artifact_path = self.settings.exports_dir / f"{uuid4()}_annotated.jpg"
        if not cv2.imwrite(str(artifact_path), annotated):
            raise RuntimeError("Could not write annotated image artifact.")

        processing_ms = int((perf_counter() - start) * 1000)
        return AnalysisPayload(
            media_type="image",
            original_filename=original_filename,
            runway_id=runway_id,
            drone_id=drone_id,
            global_state=global_state,
            lamps=lamps,
            confidence=confidence,
            frame_count=1,
            processing_ms=processing_ms,
            angle=angle,
            artifact_url=f"/media/{artifact_path.name}",
            detections=detections,
        )

    def analyze_video(
        self,
        media_path: Path,
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        drone_metadata: tuple[float, float, float] | None,
    ) -> AnalysisPayload:
        cv2 = self._require_cv2()
        start = perf_counter()
        cap = cv2.VideoCapture(str(media_path))
        if not cap.isOpened():
            raise ValueError("Could not read uploaded video.")

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 15
        max_frames = self._video_frame_limit(fps)
        source_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_frame_count > max_frames:
            cap.release()
            raise ValueError(
                f"Uploaded video is too long. Limit is {max_frames} frames "
                f"or {self.settings.max_video_seconds} seconds."
            )
        artifact_path = self.settings.exports_dir / f"{uuid4()}_annotated.mp4"
        writer = self._open_video_writer(cv2, artifact_path, fps, frame_width, frame_height)
        if writer is None:
            cap.release()
            raise RuntimeError("Could not write annotated video artifact.")

        history = deque(maxlen=self.settings.video_history_size)
        # ByteTrack id -> [(frame_index, color_state, center_x, confidence)].
        # Drives BOTH temporal transition detection AND the final per-lamp verdict,
        # so both reference the same stable track identity (not per-frame rank).
        track_observations: dict[int, list[tuple]] = {}
        frame_count = 0
        angle = self._angle_for_media(media_path, runway_id, drone_metadata)
        last_detections: list[dict] = []

        try:
            while True:
                if frame_count >= max_frames:
                    raise ValueError(
                        f"Uploaded video is too long. Limit is {max_frames} frames "
                        f"or {self.settings.max_video_seconds} seconds."
                    )
                ok, frame = cap.read()
                if not ok:
                    break

                # ByteTrack reset on first frame so state from a previous
                # video request doesn't bleed in (audit B-MAJ-1). Subsequent
                # frames continue with persist=True for actual tracking.
                detections = self._detect_frame(
                    frame,
                    use_tracking=True,
                    reset_tracker=(frame_count == 0),
                )
                lamps = normalize_detections(detections)
                # Record each tracked lamp's colour over time so red<->white
                # switches can be detected after the loop (transition is temporal,
                # not a per-frame geometric verdict).
                for det in detections:
                    track_id = det.get("track_id")
                    color = DETECTION_CLASS_TO_STATE.get(int(det.get("class_id", -1)))
                    bbox = det.get("bbox")
                    if track_id is None or color is None or not bbox:
                        continue
                    center_x = (bbox["x1"] + bbox["x2"]) / 2
                    track_observations.setdefault(int(track_id), []).append(
                        (frame_count, color, center_x, float(det.get("confidence", 0.0)))
                    )
                frame_state = global_state_from_lamps(lamps)
                frame_confidence = confidence_from_lamps(lamps)

                history.append(frame_state)
                smoothed_state = Counter(history).most_common(1)[0][0]
                annotated = self._draw_overlay(
                    frame,
                    lamps,
                    smoothed_state,
                    frame_confidence,
                    angle.elevation_angle_deg,
                )
                writer.write(annotated)

                last_detections = detections
                frame_count += 1
        finally:
            cap.release()
            writer.release()

        if frame_count == 0:
            artifact_path.unlink(missing_ok=True)
            raise ValueError("Uploaded video did not contain readable frames.")

        final_lamps = self._aggregate_video_lamps(track_observations)
        global_state = global_state_from_lamps(final_lamps)
        confidence = confidence_from_lamps(final_lamps)
        transitions = detect_lamp_transitions(track_observations, angle.elevation_angle_deg)
        processing_ms = int((perf_counter() - start) * 1000)

        return AnalysisPayload(
            media_type="video",
            original_filename=original_filename,
            runway_id=runway_id,
            drone_id=drone_id,
            global_state=global_state,
            lamps=final_lamps,
            confidence=confidence,
            frame_count=frame_count,
            processing_ms=processing_ms,
            angle=angle,
            artifact_url=f"/media/{artifact_path.name}",
            detections=last_detections,
            transitions=transitions,
        )

    @staticmethod
    def _aggregate_video_lamps(
        track_observations: dict[int, list[tuple]],
    ) -> list[LampResult]:
        """Final per-lamp video verdict, aggregated by STABLE ByteTrack identity.

        Each lamp's colour is a majority vote over the frames its track was seen;
        tracks map to lamp 1..4 left-to-right via ``lamp_index_by_track`` (the same
        identity the transition detector uses). Keying off track id rather than the
        per-frame left-to-right rank prevents a dropped/re-ordered frame from mixing
        observations of different physical lamps. Tuples: (frame, color, center_x, conf).
        """
        index_by_track = lamp_index_by_track(track_observations)
        obs_by_index: dict[int, list[tuple]] = {}
        for tid, obs in track_observations.items():
            index = index_by_track.get(tid)
            if index is not None:
                obs_by_index[index] = obs

        final_lamps: list[LampResult] = []
        for index in range(1, 5):
            obs = obs_by_index.get(index, [])
            if not obs:
                final_lamps.append(LampResult(index=index, state="unknown", confidence=0.0))
                continue
            state = Counter(o[1] for o in obs).most_common(1)[0][0]
            matching = [o for o in obs if o[1] == state]
            confidence = round(sum(o[3] for o in matching) / len(matching), 4)
            final_lamps.append(LampResult(index=index, state=state, confidence=confidence))
        return final_lamps

    def _detect_frame(
        self,
        frame: Any,
        use_tracking: bool,
        reset_tracker: bool = False,
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
            results = self.model.track(
                frame,
                persist=not reset_tracker,
                tracker="bytetrack.yaml",
                conf=self.settings.confidence_threshold,
                device=self.device,
                verbose=False,
            )
        else:
            results = self.model.predict(
                frame,
                conf=self.settings.confidence_threshold,
                device=self.device,
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

    def _angle_for_media(
        self,
        media_path: Path,
        runway_id: str,
        drone_metadata: tuple[float, float, float] | None,
    ) -> AngleResult:
        angle_source = "request_metadata" if drone_metadata else "file_metadata"
        metadata = drone_metadata or extract_gps_metadata(media_path)
        if metadata is None:
            return unavailable_angle(
                "GPS/altitude metadata not available. Browser uploads usually preserve the original file bytes, "
                "but many exported/compressed videos and images do not contain drone telemetry."
            )
        latitude, longitude, altitude = metadata
        return compute_elevation_angles(latitude, longitude, altitude, runway_id, angle_source=angle_source)

    # BGR color map (cv2 stores BGR, not RGB). At runtime a lamp's per-frame state
    # is only red/white/unknown (the detector is two-class), so the overlay draws
    # those; white<->red transitions are reported as temporal events
    # (detect_lamp_transitions), not per-frame. The amber 'transition' entry is
    # retained so the overlay is ready should a per-frame transition state be added.
    _LAMP_COLORS: dict[str, tuple[int, int, int]] = {
        "white": (245, 245, 245),
        "red": (0, 0, 255),
        "transition": (0, 165, 255),
        "unknown": (128, 128, 128),
    }

    def _draw_overlay(
        self,
        frame: Any,
        lamps: list[LampResult],
        global_state: str,
        confidence: float,
        elevation_angle_deg: float | None,
    ) -> Any:
        cv2 = self._require_cv2()
        for lamp in lamps:
            if lamp.bbox is None:
                continue
            color = self._LAMP_COLORS.get(lamp.state, self._LAMP_COLORS["unknown"])
            cv2.rectangle(frame, (lamp.bbox.x1, lamp.bbox.y1), (lamp.bbox.x2, lamp.bbox.y2), color, 2)
            cv2.putText(
                frame,
                f"L{lamp.index}: {lamp.state} {lamp.confidence:.2f}",
                (lamp.bbox.x1, max(24, lamp.bbox.y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

        angle_text = "angle: unavailable" if elevation_angle_deg is None else f"angle: {elevation_angle_deg:.3f} deg"
        lines = [
            f"PAPI: {global_state}",
            f"confidence: {confidence:.2f}",
            angle_text,
        ]
        y = 40
        for line in lines:
            cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
            y += 36
        return frame

    @staticmethod
    def _require_cv2():
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed. Run `pip install -r requirements.txt`.") from exc
        return cv2

    def _video_frame_limit(self, fps: float) -> int:
        frame_limit = max(1, self.settings.max_video_frames)
        if self.settings.max_video_seconds <= 0:
            return frame_limit
        seconds_limit = max(1, int(fps * self.settings.max_video_seconds))
        return min(frame_limit, seconds_limit)


@lru_cache
def get_inference_service() -> InferenceService:
    from app.config import get_settings

    return InferenceService(get_settings())
