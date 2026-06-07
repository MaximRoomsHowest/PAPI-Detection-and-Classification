import os
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.services.inference.aggregation import aggregate_video_lamps
from app.services.inference.angle_resolver import (
    angle_for_media,
    angle_from_samples,
    build_angle_track,
    evenly_spaced,
    resolve_drone_samples,
)
from app.services.inference.cv2_loader import require_cv2
from app.services.inference.detector import detect_frame
from app.services.inference.frame_source import (
    check_pixel_budget,
    iter_video_frames,
    video_frame_limit,
)
from app.services.inference.overlay import LAMP_COLORS, draw_overlay
from app.services.inference.sequence_runner import run_tracked_sequence
from app.services.inference.video_writer import open_video_writer
from app.services.model_registry import compute_sha256, load_model_card
from app.services.state import (
    confidence_from_lamps,
    global_state_from_lamps,
    normalize_detections,
)
from app.services.telemetry import DroneSample
from app.validation.schemas import (
    AnalysisPayload,
    AngleResult,
    AngleSample,
    LampResult,
    ModelInfo,
    ValMetrics,
)


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

    def _check_pixel_budget(self, width: int, height: int, what: str = "image") -> None:
        """Delegates to ``frame_source.check_pixel_budget`` (kept as a method so the
        decompression-bomb guard stays reachable via the service surface + tests)."""
        check_pixel_budget(width, height, self.settings.max_image_megapixels, what)

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
        self._check_pixel_budget(frame.shape[1], frame.shape[0], "image")

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
        try:
            self._check_pixel_budget(frame_width, frame_height, "video frame")
        except ValueError:
            cap.release()
            raise
        # cap.get(FPS) can return 0, a negative, or NaN for some containers; `NaN or 15`
        # keeps the NaN (NaN is truthy), which then poisons the frame-limit math and
        # surfaces as a leaked 500. Reject all three and clamp an absurd upper bound.
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not (fps and fps > 0 and fps == fps):  # `fps == fps` is False only for NaN
            fps = 15.0
        fps = min(fps, 240.0)
        max_frames = self._video_frame_limit(fps)
        too_long = (
            f"Uploaded video is too long. Limit is {max_frames} frames "
            f"or {self.settings.max_video_seconds} seconds."
        )
        source_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_frame_count > max_frames:
            cap.release()
            raise ValueError(too_long)

        # Release the capture deterministically even if the core raises mid-stream
        # (e.g. the in-loop too-long guard) — a generator's finally would only run on GC.
        # Resolving telemetry/angle stays inside the try too, so a missing-runway
        # ValueError (e.g. a runway deleted concurrently) can't leak the capture handle.
        try:
            # Resolve the telemetry fixes ONCE up front (file track > manual fix > EXIF)
            # so the tracked core can both stamp a representative angle on the overlay and
            # build the per-frame angle track after the frame count is known.
            resolved_samples, angle_source = self._resolve_drone_samples(media_path, drone_metadata, drone_samples)
            angle = self._angle_from_samples(resolved_samples, angle_source, runway_id)
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
        """Delegates to ``frame_source.iter_video_frames``."""
        return iter_video_frames(cap)

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
            self._check_pixel_budget(first.shape[1], first.shape[0], "image")
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
                    self._check_pixel_budget(frame.shape[1], frame.shape[0], "image")
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

        Delegates to ``sequence_runner.run_tracked_sequence``, injecting the loaded
        model (via ``self._detect_frame``), the cv2 handle, and the relevant settings
        so the core never imports the service (one-way leaf -> service dependency).
        """
        return run_tracked_sequence(
            frames,
            detect=self._detect_frame,
            cv2=self._require_cv2(),
            fps=fps,
            width=width,
            height=height,
            runway_id=runway_id,
            original_filename=original_filename,
            drone_id=drone_id,
            angle=angle,
            start=start,
            max_frames=max_frames,
            too_long_message=too_long_message,
            empty_message=empty_message,
            history_size=self.settings.video_history_size,
            exports_dir=self.settings.exports_dir,
            drone_samples=drone_samples,
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
        """Delegates to ``detector.detect_frame``, binding the loaded model + the
        configured confidence threshold + resolved device. ``warmup`` and the
        tracked-sequence core both reach YOLO through here."""
        return detect_frame(
            self.model,
            frame,
            use_tracking=use_tracking,
            reset_tracker=reset_tracker,
            conf=self.settings.confidence_threshold,
            device=self.device,
        )

    @staticmethod
    def _resolve_drone_samples(
        media_path: Path,
        drone_metadata: tuple[float, float, float] | None,
        drone_samples: list[DroneSample] | None,
    ) -> tuple[list[DroneSample] | None, str | None]:
        """Delegates to ``angle_resolver.resolve_drone_samples`` (telemetry-file >
        manual fix > embedded EXIF priority)."""
        return resolve_drone_samples(media_path, drone_metadata, drone_samples)

    def _angle_from_samples(
        self,
        samples: list[DroneSample] | None,
        angle_source: str | None,
        runway_id: str,
    ) -> AngleResult:
        """Delegates to ``angle_resolver.angle_from_samples`` (representative midpoint angle)."""
        return angle_from_samples(samples, angle_source, runway_id)

    def _angle_for_media(
        self,
        media_path: Path,
        runway_id: str,
        drone_metadata: tuple[float, float, float] | None,
        drone_samples: list[DroneSample] | None = None,
    ) -> AngleResult:
        """Delegates to ``angle_resolver.angle_for_media`` (single-fix angle for an image)."""
        return angle_for_media(media_path, runway_id, drone_metadata, drone_samples)

    def _build_angle_track(
        self,
        drone_samples: list[DroneSample] | None,
        runway_id: str,
        frame_count: int,
        track_observations: dict[int, list[tuple]],
    ) -> tuple[list[AngleSample], dict[int, float]]:
        """Delegates to ``angle_resolver.build_angle_track`` (per-frame angle sweep)."""
        return build_angle_track(drone_samples, runway_id, frame_count, track_observations)

    @staticmethod
    def _evenly_spaced(items: list[int], cap: int) -> list[int]:
        """Delegates to ``angle_resolver.evenly_spaced``."""
        return evenly_spaced(items, cap)

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
        """Delegates to ``frame_source.video_frame_limit``."""
        return video_frame_limit(fps, self.settings.max_video_frames, self.settings.max_video_seconds)


@lru_cache
def get_inference_service() -> InferenceService:
    from app.config import get_settings

    return InferenceService(get_settings())
