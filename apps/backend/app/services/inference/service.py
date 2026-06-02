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
from app.services.inference.aggregation import aggregate_video_lamps
from app.services.inference.cv2_loader import require_cv2
from app.services.inference.overlay import LAMP_COLORS, draw_overlay
from app.services.inference.video_writer import open_video_writer
from app.services.model_registry import compute_sha256, load_model_card
from app.services.state import (
    DETECTION_CLASS_TO_STATE,
    confidence_from_lamps,
    detect_lamp_transitions,
    global_state_from_lamps,
    lamp_index_by_track,
    normalize_detections,
)
from app.services.telemetry import DroneSample, resample_to_frames
from app.validation.schemas import (
    AnalysisPayload,
    AngleResult,
    AngleSample,
    FrameLampState,
    FramePoint,
    LampResult,
    ModelInfo,
    ValMetrics,
)

# Cap the per-frame angle track surfaced to the client. The exact red<->white
# crossing is carried separately by transitions[] (full frame resolution), so the
# track only needs enough points to draw a smooth sweep; evenly downsampling a long
# clip keeps the payload lean. Demo videos are usually well under this.
_MAX_ANGLE_TRACK_POINTS = 240


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
        drone_samples: list[DroneSample] | None = None,
    ) -> AnalysisPayload:
        # Serialise the whole inference so concurrent threadpool requests never
        # share the YOLO/ByteTrack state mid-stream (audit H1).
        with self._lock:
            if media_type == "image":
                return self.analyze_image(
                    media_path, runway_id, original_filename, drone_id, drone_metadata, drone_samples
                )
            if media_type == "video":
                return self.analyze_video(
                    media_path, runway_id, original_filename, drone_id, drone_metadata, drone_samples
                )
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
    def _open_video_writer(
        cv2: Any, base_path: Path, fps: float, width: int, height: int
    ) -> tuple[Any, Path] | tuple[None, None]:
        """Delegates to ``video_writer.open_video_writer`` (kept as a method so the
        codec policy stays reachable via the service surface)."""
        return open_video_writer(cv2, base_path, fps, width, height)

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
        drone_samples: list[DroneSample] | None = None,
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
        angle = self._angle_for_media(media_path, runway_id, drone_metadata, drone_samples)
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
        drone_samples: list[DroneSample] | None = None,
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
        too_long = (
            f"Uploaded video is too long. Limit is {max_frames} frames "
            f"or {self.settings.max_video_seconds} seconds."
        )
        source_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_frame_count > max_frames:
            cap.release()
            raise ValueError(too_long)

        # Resolve the telemetry fixes ONCE up front (file track > manual fix > EXIF)
        # so the tracked core can both stamp a representative angle on the overlay and
        # build the per-frame angle track after the frame count is known.
        resolved_samples, angle_source = self._resolve_drone_samples(media_path, drone_metadata, drone_samples)
        angle = self._angle_from_samples(resolved_samples, angle_source, runway_id)
        # Release the capture deterministically even if the core raises mid-stream
        # (e.g. the in-loop too-long guard) — a generator's finally would only run on GC.
        try:
            return self._run_tracked_sequence(
                self._iter_video_frames(cap),
                fps=fps,
                width=frame_width,
                height=frame_height,
                runway_id=runway_id,
                original_filename=original_filename,
                drone_id=drone_id,
                angle=angle,
                drone_samples=resolved_samples,
                start=start,
                max_frames=max_frames,
                too_long_message=too_long,
                empty_message="Uploaded video did not contain readable frames.",
            )
        finally:
            cap.release()

    @staticmethod
    def _iter_video_frames(cap: Any):
        """Yield decoded BGR frames from an open ``cv2.VideoCapture``.

        Releasing the capture is the CALLER's job (``analyze_video`` does it in a
        ``finally``) so an early raise in the tracked-sequence core can't leak the handle.
        """
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame

    def analyze_frame_sequence(
        self,
        image_paths: list[Path],
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        drone_metadata: tuple[float, float, float] | None,
        drone_samples: list[DroneSample] | None = None,
    ) -> AnalysisPayload:
        """Treat an ordered list of images as consecutive video frames (folder->video).

        A folder upload is analysed exactly like a video — ByteTrack continuity +
        temporal red<->white transitions + a single annotated WebM artifact — by
        feeding the images through the SAME tracked-sequence core as ``analyze_video``.
        Frames are sized to the first image; a synthetic FPS (``PAPI_SEQUENCE_FPS``)
        drives playback/timing. The viewing angle is read once from the first image's
        EXIF (or the request's drone telemetry), mirroring the one-angle-per-video model.
        """
        cv2 = self._require_cv2()
        # Serialise like analyze() does for image/video: the shared YOLO/ByteTrack
        # state is not thread-safe (audit H1). The lock is re-entrant, so self.model
        # / _detect_frame can re-acquire it while we hold it.
        with self._lock:
            start = perf_counter()
            if not image_paths:
                raise ValueError("No images were supplied for sequence analysis.")
            first = cv2.imread(str(image_paths[0]))
            if first is None:
                raise ValueError("Could not read the first image in the sequence.")
            height, width = first.shape[:2]
            fps = float(self.settings.sequence_fps)
            max_frames = max(1, self.settings.max_batch_frames)
            too_long = f"Image sequence is too long. Limit is {max_frames} frames."
            # A geotagged folder is a descent sweep: prefer an explicit telemetry
            # track, else the first image's EXIF / the manual fix. The per-frame
            # track is built from the resolved samples after the frame count is known.
            resolved_samples, angle_source = self._resolve_drone_samples(
                image_paths[0], drone_metadata, drone_samples
            )
            angle = self._angle_from_samples(resolved_samples, angle_source, runway_id)

            def frames():
                for path in image_paths:
                    frame = cv2.imread(str(path))
                    if frame is None:
                        # Skip an unreadable frame rather than abort the whole run;
                        # _run_tracked_sequence raises if NONE were readable.
                        continue
                    if frame.shape[:2] != (height, width):
                        # The VideoWriter needs a fixed size; normalise odd frames
                        # to the first image's dimensions.
                        frame = cv2.resize(frame, (width, height))
                    yield frame

            return self._run_tracked_sequence(
                frames(),
                fps=fps,
                width=width,
                height=height,
                runway_id=runway_id,
                original_filename=original_filename,
                drone_id=drone_id,
                angle=angle,
                drone_samples=resolved_samples,
                start=start,
                max_frames=max_frames,
                too_long_message=too_long,
                empty_message="None of the uploaded images could be read.",
            )

    def _run_tracked_sequence(
        self,
        frames,
        *,
        fps: float,
        width: int,
        height: int,
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        angle: AngleResult,
        start: float,
        max_frames: int,
        too_long_message: str,
        empty_message: str,
        drone_samples: list[DroneSample] | None = None,
    ) -> AnalysisPayload:
        """Source-agnostic tracked-video core shared by ``analyze_video`` (frames from a
        ``VideoCapture``) and ``analyze_frame_sequence`` (frames from a folder of images).

        Runs ByteTrack detection per frame, writes the annotated artifact, and aggregates
        the final per-lamp verdict + temporal transitions by STABLE track identity.
        ``frames`` yields BGR frames already sized to ``width`` x ``height``.
        """
        cv2 = self._require_cv2()
        base_path = self.settings.exports_dir / f"{uuid4()}_annotated"
        writer, artifact_path = self._open_video_writer(cv2, base_path, fps, width, height)
        if writer is None:
            raise RuntimeError("Could not write annotated video artifact.")

        history = deque(maxlen=self.settings.video_history_size)
        # ByteTrack id -> [(frame_index, color_state, center_x, confidence)].
        # Drives BOTH temporal transition detection AND the final per-lamp verdict,
        # so both reference the same stable track identity (not per-frame rank).
        track_observations: dict[int, list[tuple]] = {}
        frame_count = 0
        last_detections: list[dict] = []
        # Raw per-frame verdict + confidence series (one entry per processed frame),
        # surfaced on the payload so the Live Demo can chart frame-by-frame confidence.
        per_frame: list[FramePoint] = []

        # The annotated artifact is partially written as the loop runs. If the loop
        # raises (in-loop too-long guard) OR finishes with no readable frames, that
        # partial file must NOT survive as an orphan: release the writer AND unlink
        # it before re-raising. A SUCCESSFUL run releases the writer and keeps the
        # artifact (audit: orphaned-annotated-artifact on max_frames exceeded).
        try:
            for frame in frames:
                if frame_count >= max_frames:
                    raise ValueError(too_long_message)

                # ByteTrack reset on the first frame so state from a previous
                # request doesn't bleed in (audit B-MAJ-1). Subsequent frames
                # continue with persist=True for actual tracking.
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
                # Raw per-frame sample (before the sliding-window smoothing used for
                # the overlay) — the genuine frame-to-frame confidence the UI plots.
                per_frame.append(
                    FramePoint(frame_index=frame_count, confidence=frame_confidence, state=frame_state)
                )

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

            if frame_count == 0:
                raise ValueError(empty_message)
        except BaseException:
            # Any failure (too-long mid-loop, empty stream, or an unexpected error)
            # discards the half-written artifact instead of leaking it to disk.
            writer.release()
            artifact_path.unlink(missing_ok=True)
            raise
        else:
            writer.release()

        final_lamps = self._aggregate_video_lamps(track_observations)
        global_state = global_state_from_lamps(final_lamps)
        confidence = confidence_from_lamps(final_lamps)
        # Per-frame angle track from the resolved telemetry (empty when no fixes or a
        # single fix): pairs each frame's viewing angle with the lamps seen there so
        # the chart can draw the real red<->white sweep. ``frame_angles`` then gives
        # each transition the angle AT its own frame (its commissioned set angle).
        angle_track, frame_angles = self._build_angle_track(
            drone_samples, runway_id, frame_count, track_observations
        )
        transitions = detect_lamp_transitions(
            track_observations, angle.elevation_angle_deg, frame_angles=frame_angles
        )
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
            per_frame=per_frame,
            angle_track=angle_track,
        )

    @staticmethod
    def _aggregate_video_lamps(
        track_observations: dict[int, list[tuple]],
    ) -> list[LampResult]:
        """Final per-lamp video verdict, aggregated by STABLE ByteTrack identity.

        Delegates to ``aggregation.aggregate_video_lamps`` (kept as a static method
        so unit tests can call ``InferenceService._aggregate_video_lamps`` directly).
        """
        return aggregate_video_lamps(track_observations)

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

    @staticmethod
    def _resolve_drone_samples(
        media_path: Path,
        drone_metadata: tuple[float, float, float] | None,
        drone_samples: list[DroneSample] | None,
    ) -> tuple[list[DroneSample] | None, str | None]:
        """Resolve telemetry fixes + a source label for the angle calc.

        Priority: an uploaded telemetry-file track > a manual lat/lon/alt fix on the
        request > the media's embedded DJI XMP / EXIF GPS. Returns ``(None, None)``
        when no source carries usable telemetry, so the caller marks the angle
        unavailable rather than inventing one.
        """
        if drone_samples:
            return drone_samples, "telemetry_file"
        if drone_metadata:
            lat, lon, alt = drone_metadata
            return [DroneSample(lat, lon, alt)], "request_metadata"
        embedded = extract_gps_metadata(media_path)
        if embedded is not None:
            lat, lon, alt = embedded
            return [DroneSample(lat, lon, alt)], "file_metadata"
        return None, None

    def _angle_from_samples(
        self,
        samples: list[DroneSample] | None,
        angle_source: str | None,
        runway_id: str,
    ) -> AngleResult:
        """Representative single elevation angle from a telemetry track.

        The MIDDLE fix is the representative position (a descent's mid-point is a fair
        one-number summary for the overlay / readout / log); the full sweep is carried
        separately by the per-frame angle track. A single fix is its own representative.
        """
        if not samples:
            return unavailable_angle(
                "GPS/altitude metadata not available. Browser uploads usually preserve the original file "
                "bytes, but many exported/compressed videos and images do not contain drone telemetry. "
                "Upload the drone's telemetry file (DJI .SRT / CSV / JSON) or enter the position manually."
            )
        rep = samples[len(samples) // 2]
        return compute_elevation_angles(
            rep.latitude, rep.longitude, rep.altitude_m, runway_id, angle_source=angle_source or "metadata"
        )

    def _angle_for_media(
        self,
        media_path: Path,
        runway_id: str,
        drone_metadata: tuple[float, float, float] | None,
        drone_samples: list[DroneSample] | None = None,
    ) -> AngleResult:
        """Single-fix elevation angle for an image (or any non-tracked media)."""
        samples, source = self._resolve_drone_samples(media_path, drone_metadata, drone_samples)
        return self._angle_from_samples(samples, source, runway_id)

    def _build_angle_track(
        self,
        drone_samples: list[DroneSample] | None,
        runway_id: str,
        frame_count: int,
        track_observations: dict[int, list[tuple]],
    ) -> tuple[list[AngleSample], dict[int, float]]:
        """Per-frame angle track + a frame_index -> midpoint-angle map.

        Aligns the telemetry track to the processed frames (``resample_to_frames``),
        computes the PAPI-midpoint elevation angle per frame, and tags each frame with
        the lamps observed there (stable ByteTrack identity). With fewer than two
        fixes there is nothing to sweep, so an empty track + map is returned and the
        single representative angle on the payload covers it. The surfaced track is
        evenly downsampled to ``_MAX_ANGLE_TRACK_POINTS``; the full-resolution
        ``frame_angles`` map still tags every transition with the angle at its frame.
        """
        if not drone_samples or len(drone_samples) < 2 or frame_count <= 0:
            return [], {}

        resampled = resample_to_frames(drone_samples, frame_count)
        # Cache midpoint angle by (lat, lon, alt): nearest-frame resampling reuses the
        # same fix across several frames, so this avoids recomputing identical angles.
        cache: dict[tuple[float, float, float], float | None] = {}
        frame_angles: dict[int, float] = {}
        for frame_index, sample in enumerate(resampled):
            key = (sample.latitude, sample.longitude, sample.altitude_m)
            if key not in cache:
                cache[key] = compute_elevation_angles(
                    sample.latitude, sample.longitude, sample.altitude_m, runway_id
                ).elevation_angle_deg
            angle_deg = cache[key]
            if angle_deg is not None:
                frame_angles[frame_index] = round(angle_deg, 6)

        # Per-frame per-lamp colour by stable identity, so each angle sample lists the
        # lamps actually seen at that frame.
        index_by_track = lamp_index_by_track(track_observations)
        frame_lamps: dict[int, dict[int, tuple[str, float]]] = {}
        for track_id, observations in track_observations.items():
            lamp_index = index_by_track.get(track_id)
            if lamp_index is None:
                continue
            for frame_idx, color, _center_x, conf in observations:
                frame_lamps.setdefault(frame_idx, {})[lamp_index] = (color, float(conf))

        kept = self._evenly_spaced(sorted(frame_angles), _MAX_ANGLE_TRACK_POINTS)
        track = [
            AngleSample(
                frame_index=frame_index,
                elevation_angle_deg=frame_angles[frame_index],
                lamps=[
                    FrameLampState(index=idx, state=state, confidence=round(conf, 4))
                    for idx, (state, conf) in sorted(frame_lamps.get(frame_index, {}).items())
                ],
            )
            for frame_index in kept
        ]
        return track, frame_angles

    @staticmethod
    def _evenly_spaced(items: list[int], cap: int) -> list[int]:
        """Down-sample a sorted list to at most ``cap`` evenly-spaced entries (endpoints kept)."""
        if cap <= 0 or len(items) <= cap:
            return items
        step = (len(items) - 1) / (cap - 1)
        return [items[index] for index in sorted({round(i * step) for i in range(cap)})]

    # Retained on the class so the BGR overlay palette stays reachable via the
    # service surface; the canonical definition lives in ``overlay.LAMP_COLORS``.
    _LAMP_COLORS: dict[str, tuple[int, int, int]] = LAMP_COLORS

    def _draw_overlay(
        self,
        frame: Any,
        lamps: list[LampResult],
        global_state: str,
        confidence: float,
        elevation_angle_deg: float | None,
    ) -> Any:
        return draw_overlay(
            self._require_cv2(),
            frame,
            lamps,
            global_state,
            confidence,
            elevation_angle_deg,
        )

    @staticmethod
    def _require_cv2():
        return require_cv2()

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
