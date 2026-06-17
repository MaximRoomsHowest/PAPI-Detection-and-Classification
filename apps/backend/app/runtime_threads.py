"""Bound every inference thread pool to the host's real CPU allotment.

Nothing in the backend used to set CPU thread counts, so PyTorch / OpenBLAS / MKL,
ONNX Runtime, and OpenVINO each default to one thread per HOST core. Inside a
fractional-CPU cgroup — e.g. the 2.0-CPU Azure Container Apps replica — that
oversubscribes the quota and thrashes, adding latency for no benefit. This module
resolves the real allotment and pins ALL THREE inference engines to it:

  * torch + OpenCV       -> set_num_threads / cv2.setNumThreads (read *_NUM_THREADS env too)
  * ONNX Runtime         -> SessionOptions.intra_op_num_threads (its own pool; ignores OMP)
  * OpenVINO CPU plugin  -> compile_model INFERENCE_NUM_THREADS (oneTBB; also ignores OMP)

ORT and OpenVINO each ship their OWN threadpool (not OpenMP), so the *_NUM_THREADS env
vars and torch.set_num_threads do NOT reach them — hence the two monkeypatch installers.

Mirrors the proven training-script pattern (workflows/scripts/train_detector_model.py):
the *_NUM_THREADS env vars are read by OpenMP/MKL/OpenBLAS at import time, so
``configure_thread_env`` must run *before* torch is first imported; ``apply_runtime_threads``
+ the ORT/OpenVINO installers then set the engine-specific knobs once those libs load.
Everything is best-effort: a missing library or a late call is logged at debug, never
fatal — serving must survive on any hardware. The change is numerically inert: it alters
thread scheduling, not output.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Env vars consumed by the native math libraries libtorch links against (OpenMP / MKL /
# OpenBLAS / NumExpr). They must be set before the first ``import torch`` to take effect.
_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)

# Intra-op width for the ONNX Runtime monkeypatch; updated by ``install_ort_thread_limit``.
_ort_intra_threads: int = 0
_ort_patched: bool = False

# Inference width for the OpenVINO monkeypatch; updated by ``install_ov_thread_limit``.
_ov_threads: int = 0
_ov_patched: bool = False


def _cgroup_quota_cpus() -> int | None:
    """Effective CPU count from a Linux cgroup CFS *quota* (Docker --cpus / ACA cpu:N), or None.

    ``os.sched_getaffinity`` reflects the cpuset *affinity mask*, NOT the CFS bandwidth quota:
    a container limited purely by ``--cpus 2`` keeps a full-host affinity mask but is throttled
    to 2 cpu-seconds/sec. We read the quota directly so auto-mode is correct on quota-limited
    containers too (cgroup v2 cpu.max, then v1 cfs_quota_us/cfs_period_us). Returns the ceil of
    quota/period, or None when there is no finite quota / not on Linux.
    """
    try:  # cgroup v2
        with open("/sys/fs/cgroup/cpu.max", encoding="ascii") as fh:
            parts = fh.read().split()
        if len(parts) == 2 and parts[0] != "max":
            quota, period = int(parts[0]), int(parts[1])
            if quota > 0 and period > 0:
                return max(1, (quota + period - 1) // period)
    except (OSError, ValueError):
        pass
    try:  # cgroup v1
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us", encoding="ascii") as fh:
            quota = int(fh.read().strip())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us", encoding="ascii") as fh:
            period = int(fh.read().strip())
        if quota > 0 and period > 0:
            return max(1, (quota + period - 1) // period)
    except (OSError, ValueError):
        pass
    return None


def resolve_thread_count(configured: int) -> int:
    """Resolve the inference thread budget. Always returns >= 1.

    ``configured > 0`` wins verbatim. ``0`` means auto: take the MIN of the cgroup affinity
    mask (``os.sched_getaffinity`` — cpuset limits) and the cgroup CFS quota (``--cpus`` /
    ACA cpu:N), falling back to ``os.cpu_count()`` off Linux. Using the min of both makes auto
    correct under either cgroup limiting style; ``os.cpu_count()`` alone is wrong on Linux
    because it ignores BOTH cgroup mechanisms — the oversubscription this module exists to fix.
    """
    if configured and configured > 0:
        return configured
    count: int | None = None
    if hasattr(os, "sched_getaffinity"):  # Linux only — cpuset affinity mask
        try:
            count = len(os.sched_getaffinity(0))
        except OSError:
            count = None
    quota = _cgroup_quota_cpus()  # Linux CFS quota (None elsewhere / when unlimited)
    if quota is not None:
        count = quota if count is None else min(count, quota)
    if not count:
        count = os.cpu_count()
    return max(1, count or 1)


def set_thread_env(n: int) -> None:
    """Export the native-math ``*_NUM_THREADS`` env vars. Must run before torch import."""
    for var in _THREAD_ENV_VARS:
        os.environ[var] = str(n)


def configure_thread_env(configured: int) -> int:
    """Resolve the thread budget and export the env vars (imports no torch).

    Call as early as possible — before the first torch import — so OpenMP/MKL/OpenBLAS
    pick up the bound at their import time. Returns the resolved count so the caller can
    later apply the engine knobs via ``apply_runtime_threads`` / ``install_ort_thread_limit`` /
    ``install_ov_thread_limit`` once torch / onnxruntime / openvino are about to load.
    """
    n = resolve_thread_count(configured)
    set_thread_env(n)
    return n


def apply_runtime_threads(n: int) -> None:
    """Pin the torch and OpenCV thread pools to ``n``. Best-effort; call once at startup."""
    try:
        import torch

        torch.set_num_threads(n)
        # Inference is serialized by the service RLock, so there is no inter-op parallelism
        # to exploit — a 1-thread interop pool avoids spinning up an unused pool. It can only
        # be set once and before any parallel work has started, hence the inner guard.
        try:
            torch.set_num_interop_threads(1)
        except Exception as exc:  # noqa: BLE001 - already-started / already-set is harmless
            logger.debug("torch.set_num_interop_threads skipped: %s", exc)
    except Exception as exc:  # noqa: BLE001 - torch is heavy and optional in some dev envs
        logger.debug("Could not set torch thread count: %s", exc)
    try:
        import cv2

        cv2.setNumThreads(n)
    except Exception as exc:  # noqa: BLE001 - opencv variant / headless differences
        logger.debug("Could not set OpenCV thread count: %s", exc)


def install_ort_thread_limit(n: int) -> None:
    """Bound the ONNX Runtime intra-op pool to ``n`` — the only lever for ORT.

    Ultralytics constructs the session as ``InferenceSession(weight, providers=...)`` with
    NO ``SessionOptions`` (``ultralytics/nn/backends/onnx.py``), and ORT's default intra-op
    pool is its own (non-OpenMP) pool sized to host cores — so the torch/OMP settings above
    never reach it. We subclass ``InferenceSession`` to inject a ``SessionOptions`` with
    ``intra_op_num_threads=n`` (and disable intra-op spinning, which otherwise busy-waits a
    whole core between ops under a tight quota) whenever the caller passes none. Idempotent;
    a no-op when onnxruntime isn't importable (the ``.pt``-only / CUDA paths never hit it).
    """
    global _ort_intra_threads, _ort_patched
    _ort_intra_threads = n
    if _ort_patched:
        return
    try:
        import onnxruntime
    except Exception as exc:  # noqa: BLE001 - onnxruntime only present on the ONNX path
        logger.debug("onnxruntime not importable; ORT thread limit not installed: %s", exc)
        return

    orig_session = onnxruntime.InferenceSession

    class _BoundedThreadSession(orig_session):  # type: ignore[misc, valid-type]
        def __init__(self, *args: object, **kwargs: object) -> None:
            caller_set_opts = (kwargs.get("sess_options") is not None) or (
                len(args) >= 2 and args[1] is not None
            )
            if not caller_set_opts and _ort_intra_threads > 0:
                opts = onnxruntime.SessionOptions()
                opts.intra_op_num_threads = _ort_intra_threads
                opts.inter_op_num_threads = 1
                # Stop the intra-op pool busy-waiting a core between ops under a 2-CPU quota.
                try:
                    opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
                except Exception as exc:  # noqa: BLE001 - older ORT may lack the key
                    logger.debug("ORT allow_spinning config not applied: %s", exc)
                kwargs["sess_options"] = opts
            super().__init__(*args, **kwargs)

    onnxruntime.InferenceSession = _BoundedThreadSession
    _ort_patched = True
    logger.debug("ONNX Runtime intra-op threads bounded to %d.", n)


def install_ov_thread_limit(n: int) -> None:
    """Bound the OpenVINO CPU inference pool to ``n`` — the only lever for OpenVINO.

    OpenVINO's CPU plugin uses oneTBB (not OpenMP), so it ignores ``OMP_NUM_THREADS`` and
    every torch/ORT setting; empirically it sizes its pool to the host cores even with
    ``OMP_NUM_THREADS=2``. Ultralytics compiles with only ``{"PERFORMANCE_HINT": "LATENCY"}``
    and no thread cap (``ultralytics/nn/backends/openvino.py``), so on a fractional-CPU cgroup
    it oversubscribes. We wrap ``openvino.Core.compile_model`` to inject
    ``INFERENCE_NUM_THREADS=n`` + ``NUM_STREAMS=1`` while preserving the caller's hints
    (notably LATENCY). Idempotent; a no-op when openvino isn't importable (local/CI, CUDA).
    """
    global _ov_threads, _ov_patched
    _ov_threads = n
    if _ov_patched:
        return
    try:
        import openvino
    except Exception as exc:  # noqa: BLE001 - openvino is cloud-only / absent on most hosts
        logger.debug("openvino not importable; OV thread limit not installed: %s", exc)
        return

    orig_compile = openvino.Core.compile_model

    def _bounded_compile(self, model, device_name=None, config=None, **kwargs):  # type: ignore[no-untyped-def]
        if _ov_threads > 0:
            merged = dict(config or {})
            merged.setdefault("INFERENCE_NUM_THREADS", str(_ov_threads))
            merged.setdefault("NUM_STREAMS", "1")
            config = merged
        if device_name is None:
            return orig_compile(self, model, config=config, **kwargs)
        return orig_compile(self, model, device_name, config, **kwargs)

    try:
        openvino.Core.compile_model = _bounded_compile
        _ov_patched = True
        logger.debug("OpenVINO inference threads bounded to %d.", n)
    except Exception as exc:  # noqa: BLE001 - C-extension attribute may resist patching
        logger.debug("Could not patch openvino.Core.compile_model: %s", exc)
