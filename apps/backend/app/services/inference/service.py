import logging
import os
import threading
from contextlib import contextmanager
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
from app.services.model_registry import (
    REPO_ROOT,
    ModelRegistry,
    ModelRegistryEntry,
    compute_sha256,
    load_model_card,
    load_model_registry,
)
from app.services.state import (
    confidence_from_lamps,
    global_state_from_lamps,
    infer_single_missing_lamp_from_angle,
    normalize_detections,
)
from app.services.storage import get_media_storage
from app.services.telemetry import DroneSample
from app.validation.schemas import (
    AnalysisPayload,
    AngleResult,
    AngleSample,
    LampResult,
    ModelInfo,
    ValMetrics,
)

logger = logging.getLogger(__name__)

# Lock-wait visibility thresholds for _acquire_inference_lock. Inference is
# serialized by design, so a request queued behind a long video analysis can
# legitimately wait minutes — these only make that wait OBSERVABLE in the logs
# (queued vs hung is undebuggable otherwise). Constants, not env knobs.
_LOCK_WAIT_INFO_S = 0.1
_LOCK_WAIT_WARN_S = 5.0


class InferenceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._registry: ModelRegistry = load_model_registry(settings)
        self._models: dict[str, Any] = {}
        self._loaded_at: dict[str, str] = {}
        self._loaded_sha256: dict[str, str | None] = {}
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

    @contextmanager
    def _acquire_inference_lock(self):
        """Acquire the serialization lock, logging how long the caller waited.

        Used only at the TOP-LEVEL entry points (analyze / analyze_frame_sequence)
        — re-entrant acquisitions inside a held lock (_load_model, self.model)
        stay on the plain ``with self._lock`` and log nothing, since they never
        actually wait.
        """
        wait_start = perf_counter()
        with self._lock:
            waited = perf_counter() - wait_start
            if waited >= _LOCK_WAIT_WARN_S:
                logger.warning(
                    "Inference lock wait: %.1fs — request was queued behind another analysis.",
                    waited,
                )
            elif waited >= _LOCK_WAIT_INFO_S:
                logger.info("Inference lock wait: %.2fs", waited)
            yield

    def analyze(
        self,
        media_path: Path,
        media_type: str,
        runway_id: str,
        original_filename: str,
        drone_id: str | None = None,
        drone_metadata: tuple[float, float, float] | None = None,
        drone_samples: list[DroneSample] | None = None,
        transition_method: str | None = None,
        model_id: str | None = None,
    ) -> AnalysisPayload:
        # Serialise the whole inference so concurrent threadpool requests never
        # share the YOLO/ByteTrack state mid-stream (audit H1).
        with self._acquire_inference_lock():
            if media_type == "image":
                return self.analyze_image(
                    media_path, runway_id, original_filename, drone_id, drone_metadata,
                    drone_samples, transition_method, model_id,
                )
            if media_type == "video":
                return self.analyze_video(
                    media_path, runway_id, original_filename, drone_id, drone_metadata,
                    drone_samples, transition_method, model_id,
                )
            raise ValueError(f"Unsupported media type: {media_type}")

    @property
    def is_loaded(self) -> bool:
        """Whether the YOLO weights are loaded in memory (for the readiness probe)."""
        return self._registry.default_model_id in self._models

    @property
    def default_weights_present(self) -> bool:
        """Whether the registry default's weights exist on disk — the file the service
        will actually load, which can differ from settings.model_path when the registry
        designates another default (audit DEF-1; used by /health/ready)."""
        try:
            return self._registry.get().exists
        except KeyError:
            return False

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
        return self._load_model(self._registry.get())

    @property
    def transition_model(self) -> Any | None:
        """The optional 3-class transition model, lazy-loaded; None when unavailable."""
        entry = self._registry.transition_entry()
        if entry is None or not entry.available:
            return None
        return self._load_model(entry)

    def _load_model(self, entry: ModelRegistryEntry) -> Any:
        if not entry.available:
            reason = entry.disabled_reason or f"Model file not found: {entry.path}"
            raise RuntimeError(reason)
        if entry.id not in self._models:
            with self._lock:
                if entry.id not in self._models:
                    # Allowlist the weight type before handing the path to YOLO (which unpickles
                    # .pt weights): only ever load .pt / .onnx, so a malformed registry entry can't
                    # point the loader at an arbitrary file (audit: registry path lacks containment).
                    if entry.path.suffix.lower() not in (".pt", ".onnx"):
                        raise RuntimeError(
                            f"Refusing to load model '{entry.id}': unsupported weight type "
                            f"'{entry.path.suffix}' (only .pt and .onnx are allowed)."
                        )
                    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
                    try:
                        from ultralytics import YOLO
                    except ImportError as exc:
                        raise RuntimeError("Ultralytics is not installed. Run `pip install -r requirements.txt`.") from exc
                    self._models[entry.id] = YOLO(str(entry.path))
                    self._loaded_at[entry.id] = datetime.now(timezone.utc).isoformat()
                    # Hash at load time: compose mounts ./models read-only precisely so
                    # the checkpoint can be swapped under a running container, and the
                    # digest must describe the weights IN MEMORY, not whatever file is
                    # currently on disk (audit SHA-1).
                    self._loaded_sha256[entry.id] = compute_sha256(entry.path)
        return self._models[entry.id]

    def preload_available_models(self) -> list[str]:
        """Best-effort load of every available registry entry so a corrupt optional
        checkpoint surfaces at startup (logged) instead of mid-demo while holding the
        inference lock (audit WARM-1). Returns the ids that loaded."""
        loaded: list[str] = []
        for entry in self._registry.entries:
            if not entry.available:
                continue
            try:
                self._load_model(entry)
                loaded.append(entry.id)
            except Exception as exc:  # noqa: BLE001 - preload must never abort startup
                logger.warning("Startup preload of model '%s' failed: %s", entry.id, exc)
        return loaded

    @staticmethod
    def _is_three_class(model: Any) -> bool:
        """A model that can emit class 2 (transition) — i.e. names has >= 3 entries."""
        names = getattr(model, "names", None)
        return isinstance(names, dict) and len(names) >= 3

    def _resolve_transition(self, requested: str | None) -> tuple[Any, str]:
        """Legacy resolver kept for direct unit tests and transition_method compatibility."""
        method = (requested or self.settings.default_transition_method or "tracking").strip().lower()
        if method == "model":
            transition_model = self.transition_model
            if transition_model is not None and self._is_three_class(transition_model):
                return transition_model, "model"
            if self._is_three_class(self.model):
                return self.model, "model"
            return self.model, "tracking"
        return self.model, "tracking"

    def _resolve_selected_model(
        self, model_id: str | None, transition_method: str | None
    ) -> tuple[Any, ModelRegistryEntry, str]:
        explicit_model = model_id is not None and str(model_id).strip() != ""
        explicit_method = transition_method is not None and str(transition_method).strip() != ""

        if explicit_model:
            try:
                entry = self._registry.get(str(model_id).strip())
            except KeyError as exc:
                # Truncate the echo: model_id is unbounded client text that flows into
                # the 400 detail and the structured log (audit ECHO-1).
                raise ValueError(f"Unknown model_id: {str(model_id)[:120]}") from exc
            if not entry.available:
                reason = entry.disabled_reason or "model file is missing"
                raise ValueError(f"Model '{entry.id}' is unavailable: {reason}")
            model = self._load_model(entry)
            method = (transition_method or "").strip().lower() if explicit_method else None
            if method not in ("tracking", "model", None):
                method = "tracking"
            if method is None:
                method = "model" if entry.role == "transition" or entry.class_count >= 3 else "tracking"
            if method == "model" and not self._is_three_class(model):
                method = "tracking"
            return model, entry, method

        # When neither model_id nor transition_method is given, PAPI_TRANSITION_METHOD
        # is the documented default — it must be honoured here, not just by the legacy
        # resolver, or a deployment configured with =model silently reverts to tracking
        # (audit TRN-1). An explicit model_id wins over the setting (handled above).
        requested_method = (
            str(transition_method).strip().lower()
            if explicit_method
            else (self.settings.default_transition_method or "tracking").strip().lower()
        )
        if requested_method == "model":
            transition_entry = self._registry.transition_entry()
            if transition_entry is not None and transition_entry.available:
                model = self._load_model(transition_entry)
                if self._is_three_class(model):
                    return model, transition_entry, "model"
            model, effective_method = self._resolve_transition("model")
            return model, self._registry.get(), effective_method

        entry = self._registry.get()
        model = self._load_model(entry)
        if explicit_method:
            # An explicit "model" is handled above; any other explicit value (e.g. "tracking")
            # is HONOURED here instead of being silently recomputed from the entry's metadata (audit).
            method = "tracking"
        else:
            method = "model" if entry.role == "transition" or entry.class_count >= 3 else "tracking"
            # Verify the declared class_count against the loaded model so a mislabeled models.json
            # can't select the 3-class "model" algorithm on a 2-class detector (audit).
            if method == "model" and not self._is_three_class(model):
                method = "tracking"
        return model, entry, method

    def _model_info_for_entry(self, entry: ModelRegistryEntry) -> ModelInfo:
        path = entry.path
        suffix = path.suffix.lower().lstrip(".") or "unknown"
        backend_type = {
            "onnx": "ultralytics-onnxruntime",
            "pt": "ultralytics-pytorch",
        }.get(suffix, f"ultralytics-{suffix}")
        # stat() inside try: the file can vanish between the registry scan and now; report
        # size-unknown rather than raising a 500 on the TOCTOU race (audit).
        try:
            file_size_mb = round(path.stat().st_size / (1024 * 1024), 2)
            exists = True
        except OSError:
            file_size_mb = None
            exists = False

        # Provenance comes from models/serving/model_card.json (audit IMP-BE-1).
        # Class names are taken from the live model when loaded (authoritative),
        # otherwise from the card, otherwise None — so the endpoint stays useful
        # whether or not the weights are present.
        # Expose a repo-relative path, not the absolute server filesystem layout (audit).
        try:
            relative_path = str(path.relative_to(REPO_ROOT))
        except ValueError:
            relative_path = path.name

        card = entry.card or load_model_card(path) or {}
        # Optional metadata must never take down model discovery: a non-numeric class
        # key or a wrong-typed val_metrics field degrades that one field to None
        # instead of 500ing /api/models and blanking the selector (audit REG-2).
        classes: dict[int, str] | None = None
        loaded_model = self._models.get(entry.id)
        if loaded_model is not None:
            names = getattr(loaded_model, "names", None)
            if isinstance(names, dict):
                try:
                    classes = {int(key): str(value) for key, value in names.items()}
                except (TypeError, ValueError):
                    classes = None
        if classes is None and isinstance(card.get("classes"), dict):
            try:
                classes = {int(key): str(value) for key, value in card["classes"].items()}
            except (TypeError, ValueError):
                classes = None
        val_metrics = card.get("val_metrics")
        parsed_val_metrics: ValMetrics | None = None
        if isinstance(val_metrics, dict):
            try:
                parsed_val_metrics = ValMetrics(**val_metrics)
            except ValueError:  # pydantic ValidationError subclasses ValueError
                logger.warning("Ignoring malformed val_metrics for model '%s'.", entry.id)

        # When loaded, report the digest recorded AT LOAD TIME so it always describes
        # the in-memory model; a differing on-disk hash means an operator swapped the
        # checkpoint under the running service and a restart is pending (audit SHA-1).
        loaded = entry.id in self._models
        disk_sha256 = compute_sha256(path)
        sha256 = self._loaded_sha256.get(entry.id) if loaded else disk_sha256
        weights_changed_on_disk = (
            disk_sha256 != sha256 if loaded and sha256 is not None else None
        )

        return ModelInfo(
            model_id=entry.id,
            model_label=entry.label,
            model_role=entry.role,
            is_default=entry.default,
            available=entry.available,
            disabled_reason=None if entry.available else entry.disabled_reason or "Model file is missing.",
            description=entry.description,
            model_path=relative_path,
            model_filename=path.name,
            model_format=suffix,
            backend_type=backend_type,
            exists=exists,
            file_size_mb=file_size_mb,
            confidence_threshold=self.settings.confidence_threshold,
            device=self.device,
            loaded=loaded,
            sha256=sha256,
            weights_changed_on_disk=weights_changed_on_disk,
            classes=classes,
            model_card_id=card.get("model_id"),
            training_run=card.get("training_run"),
            base_weights=card.get("base_weights"),
            dataset_split_evaluated=card.get("split_evaluated"),
            val_metrics=parsed_val_metrics,
            loaded_at=self._loaded_at.get(entry.id),
        )

    def model_info(self, model_id: str | None = None) -> ModelInfo:
        try:
            entry = self._registry.get(model_id)
        except KeyError as exc:
            raise ValueError(f"Unknown model_id: {str(model_id)[:120]}") from exc
        return self._model_info_for_entry(entry)

    def model_options(self) -> list[ModelInfo]:
        # Per-entry isolation: one broken entry degrades to a missing option rather
        # than 500ing the whole selector list (audit REG-2).
        options: list[ModelInfo] = []
        for entry in self._registry.entries:
            try:
                options.append(self._model_info_for_entry(entry))
            except Exception:  # noqa: BLE001 - discovery must degrade, never die
                logger.exception("Skipping model option '%s': info construction failed.", entry.id)
        return options

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
        transition_method: str | None = None,
        model_id: str | None = None,
    ) -> AnalysisPayload:
        cv2 = self._require_cv2()
        start = perf_counter()
        frame = cv2.imread(str(media_path))
        if frame is None:
            raise ValueError("Could not read uploaded image.")
        self._check_pixel_budget(frame.shape[1], frame.shape[0], "image")

        # With the "model" method a 3-class detector can classify a lamp as "transition" in a
        # single frame; "tracking" uses the 2-class serving model (red/white only).
        model, selected_model, effective_method = self._resolve_selected_model(model_id, transition_method)
        detections = self._detect_frame(frame, use_tracking=False, model=model)
        # A single image yields red/white per lamp; a "transition" requires a
        # red<->white switch across frames, so there are none here. The angle is
        # still computed for display / transition association.
        angle = self._angle_for_media(media_path, runway_id, drone_metadata, drone_samples)
        lamps = infer_single_missing_lamp_from_angle(normalize_detections(detections), angle)
        global_state = global_state_from_lamps(lamps)
        confidence = confidence_from_lamps(lamps)

        annotated = self._draw_overlay(frame, lamps, global_state, confidence, angle.elevation_angle_deg)
        artifact_path = self.settings.exports_dir / f"{uuid4()}_annotated.jpg"
        if not cv2.imwrite(str(artifact_path), annotated):
            raise RuntimeError("Could not write annotated image artifact.")
        _artifact_ref, artifact_url = self._store_export_artifact(artifact_path)

        processing_ms = int((perf_counter() - start) * 1000)
        return AnalysisPayload(
            media_type="image",
            original_filename=original_filename,
            runway_id=runway_id,
            drone_id=drone_id,
            model_id=selected_model.id,
            model_label=selected_model.label,
            model_role=selected_model.role,
            global_state=global_state,
            lamps=lamps,
            confidence=confidence,
            frame_count=1,
            processing_ms=processing_ms,
            angle=angle,
            artifact_url=artifact_url,
            detections=detections,
            transition_method=effective_method,
        )

    def analyze_video(
        self,
        media_path: Path,
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        drone_metadata: tuple[float, float, float] | None,
        drone_samples: list[DroneSample] | None = None,
        transition_method: str | None = None,
        model_id: str | None = None,
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
            model, selected_model, effective_method = self._resolve_selected_model(model_id, transition_method)
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
                empty_message="Uploaded video did not contain readable frames.",
                model=model,
                selected_model=selected_model,
                transition_method=effective_method,
                expected_frame_count=source_frame_count or None,
                # CAP_PROP_FRAME_COUNT is container metadata and can be off by a
                # few frames (VFR / sloppy muxers) — only a >5% (and >2 frame)
                # gap is a real mid-stream decode failure worth flagging.
                shortfall_tolerance=max(2, source_frame_count // 20),
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
        transition_method: str | None = None,
        model_id: str | None = None,
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
        with self._acquire_inference_lock():
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

            model, selected_model, effective_method = self._resolve_selected_model(model_id, transition_method)
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
                empty_message="None of the uploaded images could be read.",
                model=model,
                selected_model=selected_model,
                transition_method=effective_method,
                # The image list is exact (unlike video container metadata), so
                # ANY skipped unreadable file is a reportable shortfall.
                expected_frame_count=len(image_paths),
                shortfall_tolerance=0,
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
        empty_message: str,
        drone_samples: list[DroneSample] | None = None,
        model: Any | None = None,
        selected_model: ModelRegistryEntry | None = None,
        transition_method: str = "tracking",
        expected_frame_count: int | None = None,
        shortfall_tolerance: int = 0,
    ) -> AnalysisPayload:
        """Source-agnostic tracked-video core shared by ``analyze_video`` (frames from a
        ``VideoCapture``) and ``analyze_frame_sequence`` (frames from a folder of images).

        Runs ByteTrack detection per frame, writes the annotated artifact, and aggregates
        the final per-lamp verdict + transitions by STABLE track identity. ``frames`` yields
        BGR frames already sized to ``width`` x ``height``. ``model`` selects the detector
        (serving 2-class or the 3-class transition model); ``transition_method`` selects how
        transitions are derived from the tracked observations.

        Delegates to ``sequence_runner.run_tracked_sequence``, injecting the chosen model
        (via ``self._detect_frame``), the cv2 handle, and the relevant settings so the core
        never imports the service (one-way leaf -> service dependency).
        """

        def detect(frame: Any, *, use_tracking: bool, reset_tracker: bool = False) -> list[dict]:
            return self._detect_frame(
                frame, use_tracking=use_tracking, reset_tracker=reset_tracker, model=model
            )

        payload = run_tracked_sequence(
            frames,
            detect=detect,
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
            empty_message=empty_message,
            exports_dir=self.settings.exports_dir,
            store_export=self._store_export_artifact,
            drone_samples=drone_samples,
            transition_method=transition_method,
            expected_frame_count=expected_frame_count,
            shortfall_tolerance=shortfall_tolerance,
        )
        if selected_model is not None:
            payload.model_id = selected_model.id
            payload.model_label = selected_model.label
            payload.model_role = selected_model.role
        return payload

    def _store_export_artifact(self, artifact_path: Path) -> tuple[str, str]:
        storage = get_media_storage(self.settings)
        try:
            reference = storage.persist_export(artifact_path)
        except Exception:
            # Azure-mode persist_export only unlinks the local file AFTER a
            # successful blob upload; on failure the request 503s and nothing
            # references the finished artifact — delete it instead of leaking
            # one orphan per transient Blob failure (local mode never raises
            # here, so this path can't delete a servable local artifact).
            artifact_path.unlink(missing_ok=True)
            raise
        artifact_url = storage.url_for_reference(reference)
        if artifact_url is None:
            raise RuntimeError("Could not create media URL for annotated artifact.")
        return reference, artifact_url

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
        model: Any | None = None,
    ) -> list[dict]:
        """Delegates to ``detector.detect_frame``, binding a model (the serving model by
        default, or the 3-class transition model for the "model" method) + the configured
        confidence threshold + resolved device. ``warmup`` and the tracked-sequence core
        both reach YOLO through here."""
        return detect_frame(
            model or self.model,
            frame,
            use_tracking=use_tracking,
            reset_tracker=reset_tracker,
            conf=self.settings.confidence_threshold,
            imgsz=self.settings.inference_imgsz,
            iou=self.settings.inference_iou,
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
