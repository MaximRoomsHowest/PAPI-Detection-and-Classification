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

from app.config import TRANSITION_METHODS, Settings
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
    build_registry_from_db,
    compute_sha256,
    load_model_card,
)
from app.services.state import (
    bind_lamps_to_runway_display,
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
    WeatherMetrics,
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
        # The registry is now DB-backed (mutable: uploads/promote/delete write rows).
        # build_registry_from_db falls back to the frozen JSON/legacy loader when the
        # DB is unreachable or the table is empty (fresh boot, no-DB dev), so startup
        # never depends on the table already existing.
        self._registry: ModelRegistry = build_registry_from_db(settings)
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
                payload = self.analyze_video(
                    media_path, runway_id, original_filename, drone_id, drone_metadata,
                    drone_samples, transition_method, model_id, defer_export=True,
                )
            else:
                raise ValueError(f"Unsupported media type: {media_type}")
        # Persist the annotated artifact AFTER releasing the lock: an Azure blob upload
        # is seconds of network I/O that must not extend the held inference lock and
        # stall a concurrent live/single-image request. Mirrors analyze_frame_sequence
        # (the folder path was already fixed; video was not — audit 2026-06-19). Local
        # mode is a no-op rewrite to the same /media URL.
        self._persist_deferred_export(payload)
        return payload

    def reload_registry(self) -> None:
        """Rebuild the registry from the DB and evict stale cached models.

        Called after every registry mutation (upload / promote / delete / disable /
        evaluation writeback). The new registry is built OUTSIDE the lock — it opens
        its own short-lived DB session — and only the dict swap + cache eviction run
        UNDER the lock, so an in-flight ``analyze()`` never observes a half-swapped
        registry and the critical section costs microseconds (no YOLO load inside it).
        Live inference simply queues briefly behind the swap on the same RLock.
        """
        new_registry = build_registry_from_db(self.settings)
        with self._lock:
            old_by_id = {entry.id: entry for entry in self._registry.entries}
            new_by_id = {entry.id: entry for entry in new_registry.entries}
            for model_id in list(self._models):
                new_entry = new_by_id.get(model_id)
                old_entry = old_by_id.get(model_id)
                # Evict a cached model if its entry vanished, if it was just disabled
                # (a disabled entry stays listed but is no longer servable, so it must
                # not linger hot in the cache), or if its resolved weights path changed
                # (an id was re-uploaded with new weights). A still-valid cached model
                # stays hot across the reload.
                if new_entry is None or new_entry.disabled or (
                    old_entry is not None and str(new_entry.path) != str(old_entry.path)
                ):
                    self._models.pop(model_id, None)
                    self._loaded_at.pop(model_id, None)
                    self._loaded_sha256.pop(model_id, None)
            self._registry = new_registry

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
        """The device passed to YOLO, expanding ``PAPI_DEVICE=auto`` to cuda when a GPU is
        available else cpu (audit IMP-SRV-2). An explicit cuda / GPU-index request is GUARDED:
        if no CUDA is present (e.g. this CPU-only image), it falls back to cpu with a warning
        instead of letting every inference 500 on a missing device while /health/ready still
        reports ready. Cached so torch is probed at most once."""
        if self._resolved_device is None:
            configured = (self.settings.device or "cpu").strip().lower()
            if configured == "auto":
                self._resolved_device = self._detect_device()
            elif self._wants_cuda(configured) and not self._cuda_available():
                logger.warning(
                    "PAPI_DEVICE=%s requested but CUDA is not available (this image ships CPU-only "
                    "torch); falling back to cpu. Build/run a CUDA-enabled image + expose a GPU to "
                    "use one.",
                    self.settings.device,
                )
                self._resolved_device = "cpu"
            else:
                self._resolved_device = configured
        return self._resolved_device

    @staticmethod
    def _wants_cuda(configured: str) -> bool:
        """True when the configured device targets a GPU: 'cuda', 'cuda:N', or a bare GPU index."""
        return configured.startswith("cuda") or configured.isdigit()

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001 - torch import/probe is best-effort
            return False

    @staticmethod
    def _detect_device() -> str:
        return "cuda" if InferenceService._cuda_available() else "cpu"

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
        if entry is None:
            return None
        if entry.id in self._models:
            return self._models[entry.id]
        if not entry.available:
            return None
        return self._load_model(entry)

    def _resolve_backend_artifact(self, entry: ModelRegistryEntry) -> Path:
        """Pick the on-disk artifact to load for ``entry`` based on the resolved device and
        the configured backend, so every hardware target gets its best path with no quality
        loss. CUDA always uses the native ``.pt`` (ONNX/OpenVINO on GPU is typically slower
        and forfeits the fp16 option). On CPU, ``auto`` prefers an OpenVINO IR SIBLING of the
        registered ``.pt`` (``best_openvino_model/``) for lower latency at parity-verified
        accuracy — measured ~1.5x faster than torch at the 2-CPU budget. ONNX is NOT part of
        ``auto``: fp32 ONNX Runtime measured ~2.2x SLOWER than torch on CPU (MLAS conv kernels),
        so an ``.onnx`` sibling is used only when ``PAPI_INFERENCE_BACKEND=onnx`` is forced. A
        missing sibling (or a non-``.pt`` entry, e.g. an uploaded ``.onnx``) is taken verbatim,
        so unusual hosts and custom models still load."""
        base = entry.path
        backend = (self.settings.inference_backend or "auto").strip().lower()
        on_cuda = self.device.lower().startswith("cuda")
        if on_cuda or backend == "pt" or base.suffix.lower() != ".pt":
            return base
        if backend in ("auto", "openvino"):
            openvino_dir = base.with_name(base.stem + "_openvino_model")
            if openvino_dir.is_dir():
                return openvino_dir
        if backend == "onnx":  # ONNX only when explicitly forced — it is slower than .pt on CPU
            onnx_path = base.with_suffix(".onnx")
            if onnx_path.is_file():
                return onnx_path
        return base

    @staticmethod
    def _is_loadable_artifact(path: Path) -> bool:
        """Allowlist the artifact type before handing it to YOLO (which unpickles ``.pt``):
        only ``.pt`` / ``.onnx`` files or an ``*_openvino_model`` directory, so a malformed
        registry entry can't point the loader at an arbitrary file (audit: path containment)."""
        if path.is_dir():
            return path.name.endswith("_openvino_model")
        return path.suffix.lower() in (".pt", ".onnx")

    def _load_model(self, entry: ModelRegistryEntry) -> Any:
        if not entry.available:
            reason = entry.disabled_reason or f"Model file not found: {entry.path}"
            raise RuntimeError(reason)
        if entry.id not in self._models:
            with self._lock:
                if entry.id not in self._models:
                    resolved = self._resolve_backend_artifact(entry)
                    if not self._is_loadable_artifact(resolved):
                        raise RuntimeError(
                            f"Refusing to load model '{entry.id}': unsupported weight type "
                            f"'{resolved.name}' (only .pt, .onnx, or an *_openvino_model dir are allowed)."
                        )
                    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
                    try:
                        from ultralytics import YOLO
                    except ImportError as exc:
                        raise RuntimeError("Ultralytics is not installed. Run `pip install -r requirements.txt`.") from exc
                    optimized = resolved != entry.path
                    try:
                        # task="detect" pins the task so an ONNX/OpenVINO artifact does not trip
                        # Ultralytics' "Unable to guess task" startup warning (every PAPI model
                        # is a detector).
                        model = YOLO(str(resolved), task="detect")
                        if optimized:
                            # Smoke-test the optimized artifact at the CONFIGURED imgsz so a
                            # static-shape / imgsz mismatch or an ISA mis-execute demotes to .pt
                            # HERE — the construction try/except alone only catches load failures,
                            # not a first-inference failure, which would otherwise 500 every request.
                            self._smoke_test_model(model)
                    except Exception as exc:  # noqa: BLE001 - any optimized-artifact failure
                        # Hardware-portability guarantee: an optimized sibling that fails to load
                        # OR fails its first inference (unusual host, corrupt/static-shape export,
                        # ORT/OpenVINO quirk) must NOT break serving — fall back to the registered
                        # .pt, which runs on every host and at any imgsz. INFO, not WARNING: this is
                        # the EXPECTED path locally where openvino isn't installed (cloud-only dep).
                        if optimized:
                            logger.info(
                                "Optimized backend '%s' unavailable for '%s' (%s); using %s.",
                                resolved.name, entry.id, exc, entry.path.name,
                            )
                            resolved = entry.path
                            model = YOLO(str(resolved), task="detect")
                        else:
                            raise
                    self._models[entry.id] = model
                    self._loaded_at[entry.id] = datetime.now(timezone.utc).isoformat()
                    # Hash at load time: compose mounts ./models read-only precisely so the
                    # checkpoint can be swapped under a running container, and the digest must
                    # describe the weights IN MEMORY (audit SHA-1). A directory artifact (OpenVINO
                    # IR) has no file digest, so hash the SOURCE .pt instead — keeps /api/model
                    # provenance + the checkpoint-swap detector working for the OpenVINO-served
                    # model rather than reporting sha256=null (audit: provenance lost for dirs).
                    digest_target = resolved if resolved.is_file() else entry.path
                    self._loaded_sha256[entry.id] = compute_sha256(digest_target)
        return self._models[entry.id]

    def _smoke_test_model(self, model: Any) -> None:
        """Run one tiny inference at the configured imgsz/device so a runtime failure (static
        OpenVINO shape vs a non-default PAPI_INFERENCE_IMGSZ, or an ISA mis-execute) surfaces at
        load time — letting ``_load_model`` fall back to .pt — instead of 500ing every request."""
        import numpy as np

        model.predict(
            np.zeros((64, 64, 3), dtype=np.uint8),
            imgsz=self.settings.inference_imgsz,
            device=self.device,
            verbose=False,
        )

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
        serving_model = self.model
        if method == "model":
            transition_model = self.transition_model
            if transition_model is not None and self._is_three_class(transition_model):
                return transition_model, "model"
            if self._is_three_class(serving_model):
                return serving_model, "model"
            return serving_model, "tracking"
        return serving_model, "tracking"

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
            if method is not None and method not in TRANSITION_METHODS:
                raise ValueError(f"transition_method must be {' or '.join(map(repr, TRANSITION_METHODS))}")
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
        if explicit_method and requested_method not in TRANSITION_METHODS:
            raise ValueError(f"transition_method must be {' or '.join(map(repr, TRANSITION_METHODS))}")
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
        # Snapshot the mutable load-state under the lock so the loaded / sha256 /
        # loaded_at / live-class-names reads below form ONE consistent view, even if a
        # concurrent reload_registry()/_load_model() mutates these dicts mid-method.
        with self._lock:
            loaded_model = self._models.get(entry.id)
            loaded = entry.id in self._models
            loaded_sha_at_load = self._loaded_sha256.get(entry.id)
            loaded_at_value = self._loaded_at.get(entry.id)

        classes: dict[int, str] | None = None
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

        weather_metrics = card.get("weather_metrics")
        parsed_weather_metrics: WeatherMetrics | None = None
        if isinstance(weather_metrics, dict):
            try:
                parsed_weather_metrics = WeatherMetrics(**weather_metrics)
            except ValueError:
                logger.warning("Ignoring malformed weather_metrics for model '%s'.", entry.id)

        # When loaded, report the digest recorded AT LOAD TIME so it always describes
        # the in-memory model; a differing on-disk hash means an operator swapped the
        # checkpoint under the running service and a restart is pending (audit SHA-1).
        disk_sha256 = compute_sha256(path)
        sha256 = loaded_sha_at_load if loaded else disk_sha256
        weights_changed_on_disk = (
            disk_sha256 != sha256 if loaded and sha256 is not None else None
        )

        if entry.available:
            disabled_reason = None
        elif entry.disabled:
            disabled_reason = entry.disabled_reason or "Disabled by operator."
        else:
            disabled_reason = entry.disabled_reason or "Model file is missing."

        return ModelInfo(
            model_id=entry.id,
            model_label=entry.label,
            model_role=entry.role,
            is_default=entry.default,
            available=entry.available,
            disabled_reason=disabled_reason,
            description=entry.description,
            source=entry.source,
            protected=entry.protected,
            disabled=entry.disabled,
            class_count=entry.class_count,
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
            weather_metrics=parsed_weather_metrics,
            loaded_at=loaded_at_value,
        )

    def model_info(self, model_id: str | None = None) -> ModelInfo:
        try:
            entry = self._registry.get(model_id)
        except KeyError as exc:
            raise ValueError(f"Unknown model_id: {str(model_id)[:120]}") from exc
        return self._model_info_for_entry(entry)

    def model_info_for_entry(self, entry: ModelRegistryEntry) -> ModelInfo:
        """Build a ModelInfo for an entry that may not be in the live registry.

        Public seam for the model-upload response fallback so it shares this one
        ModelInfo construction instead of maintaining a divergent copy.
        """
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
        """Run dummy inferences so a broken checkpoint surfaces at startup rather than on
        the first real request (audit IMP-SRV-9), and so the first real frame doesn't pay
        one-time init latency. Best-effort — the caller logs failures and never aborts
        startup."""
        import numpy as np

        dummy = np.zeros((64, 64, 3), dtype=np.uint8)
        # Single-image / per-frame predict path.
        self._detect_frame(dummy, use_tracking=False)
        # Tracked-sequence (ByteTrack) path used by video + folder analysis: model.track's
        # first call initialises the tracker. reset_tracker=True (persist=False) primes that
        # init AND leaves the tracker reset, so warmup state never bleeds into the first real
        # video (matches the per-request tracker-isolation contract). Best-effort: a tracking
        # warmup hiccup must not mask the successful detector warmup above.
        try:
            self._detect_frame(dummy, use_tracking=True, reset_tracker=True)
        except Exception:  # noqa: BLE001 - tracker warmup is best-effort only
            logger.warning("Tracking-path warmup skipped.", exc_info=True)

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

        # Images have no temporal context, so even when a 3-class model is selected
        # class-2 detections are normalized below instead of surfaced as transition events.
        model, selected_model, effective_method = self._resolve_selected_model(model_id, transition_method)
        detections = self._detect_frame(frame, use_tracking=False, model=model)
        # A single image yields red/white per lamp; a "transition" requires a
        # red<->white switch across frames, so there are none here. The angle is
        # still computed for display / transition association.
        angle = self._angle_for_media(media_path, runway_id, drone_metadata, drone_samples)
        if effective_method == "model":
            detections = [
                {**detection, "class_id": -1}
                if int(detection.get("class_id", -1)) == 2 else detection
                for detection in detections
            ]
        raw_lamps = infer_single_missing_lamp_from_angle(normalize_detections(detections), angle)
        lamps = bind_lamps_to_runway_display(raw_lamps, runway_id)
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
        defer_export: bool = False,
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
                # When called from analyze() under the held lock, keep the artifact
                # local here and let analyze() persist it after releasing the lock so a
                # slow blob upload never blocks live inference (audit 2026-06-19).
                defer_export=defer_export,
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
            payload = self._run_tracked_sequence(
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
                defer_export=True,
            )
        # Persist the artifact OUTSIDE the lock: an Azure upload (seconds of network
        # I/O) must not extend the already-long held lock and stall live single-image
        # inference. Local mode is a no-op rewrite to the same /media URL (audit #6).
        self._persist_deferred_export(payload)
        return payload

    def _persist_deferred_export(self, payload: AnalysisPayload) -> None:
        """Persist a deferred-local artifact to the media backend and rewrite the
        payload URL. Called only after the inference lock is released (folder->video).
        The local name is recoverable from the ``/media/<name>`` URL the core stamped
        when ``store_export`` was skipped.
        """
        local_name = payload.artifact_url.rsplit("/", 1)[-1]
        artifact_path = self.settings.exports_dir / local_name
        if not artifact_path.is_file():
            # The core wrote this under the lock moments ago; if it has vanished
            # (disk error / external cleanup) fail with a clear message rather than
            # a cryptic FileNotFoundError from deep inside the Azure upload.
            raise RuntimeError(f"Annotated artifact missing before export: {artifact_path}")
        _reference, payload.artifact_url = self._store_export_artifact(artifact_path)

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
        defer_export: bool = False,
    ) -> AnalysisPayload:
        """Source-agnostic tracked-video core shared by ``analyze_video`` (frames from a
        ``VideoCapture``) and ``analyze_frame_sequence`` (frames from a folder of images).

        Runs ByteTrack detection per frame, writes the annotated artifact, and derives
        the final per-lamp verdict + transitions in display Light 1..4 slots. ``frames`` yields
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
            # When the caller holds the inference lock around this whole run (the
            # folder->video path), defer the export: keep the artifact local here and
            # let the caller persist it AFTER releasing the lock, so a slow Azure blob
            # upload never blocks live inference behind the lock.
            store_export=None if defer_export else self._store_export_artifact,
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
        # fp16 only on CUDA: Ultralytics ignores half on CPU, and the flag is opt-in
        # (default off) so the default CPU deploy's numeric output is unchanged.
        half = self.settings.inference_half and self.device.lower().startswith("cuda")
        return detect_frame(
            model or self.model,
            frame,
            use_tracking=use_tracking,
            reset_tracker=reset_tracker,
            conf=self.settings.confidence_threshold,
            imgsz=self.settings.inference_imgsz,
            iou=self.settings.inference_iou,
            device=self.device,
            half=half,
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
