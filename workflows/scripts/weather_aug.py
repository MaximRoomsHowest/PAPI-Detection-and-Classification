"""Colour-safe synthetic weather augmentation for the PAPI detectors — pure OpenCV/NumPy.

Single source of truth shared by training, demo-video generation, and robustness evaluation.

**Why pure OpenCV (no albumentations).** An earlier version used AlbumentationsX; its ``albucore``
SIMD backend corrupts asynchronous CUDA training on this stack (torch 2.5.1+cu121 / driver 610.x /
RTX 4070 Laptop) — every weather-augmented run crashed with assorted CUDA faults, while Ultralytics'
own OpenCV-based mosaic augmentation ran fine. The crash is in albucore's *execution*, not its
output (Ultralytics re-copies images before the GPU). Re-implementing the effects in OpenCV/NumPy —
exactly the libraries Ultralytics itself augments with — keeps training on the fast async+AMP path
and drops the AGPL dependency. See ``install_training_hook`` and ``models/MODELS.md``.

**Colour-safe.** The class IS the colour (red vs white lamp), so every effect is a pixel-level
weather veil/overlay that never permutes hue and never converts to grayscale. Fog/haze desaturate
the whole scene uniformly — that *is* the robustness target, not a relabel. No geometry changes, so
bounding boxes are untouched.

Images are BGR uint8 (OpenCV's native order, matching what Ultralytics loads), in and out.
"""

from __future__ import annotations

import cv2
import numpy as np

# Conditions a single clip / eval split can request ("clear" is the untouched baseline).
CONDITIONS = ("clear", "rain", "fog", "haze", "snow", "sunflare", "shadow", "warm", "cool")
_WEATHER = ("rain", "fog", "haze", "snow", "sunflare", "shadow", "warm", "cool")

# Severity presets. Fog/haze are the headline degradation (the detector lost ~28 mAP50 under fog).
# Coefficients are blend/intensity weights in [0,1], clamped so the four lamps never fully wash out.
_PRESETS: dict[str, dict] = {
    "light": {
        "fog": (0.10, 0.25), "haze": (0.05, 0.15), "rain_bright": 0.92, "rain_len": (8, 16),
        "snow": (0.15, 0.35), "shadow": (0.25, 0.45), "flare": (0.40, 0.60), "tint": (0.06, 0.12),
    },
    "medium": {
        "fog": (0.25, 0.45), "haze": (0.12, 0.25), "rain_bright": 0.85, "rain_len": (12, 22),
        "snow": (0.30, 0.55), "shadow": (0.35, 0.55), "flare": (0.50, 0.75), "tint": (0.10, 0.18),
    },
    "heavy": {
        "fog": (0.40, 0.60), "haze": (0.20, 0.35), "rain_bright": 0.78, "rain_len": (16, 28),
        "snow": (0.45, 0.75), "shadow": (0.45, 0.65), "flare": (0.60, 0.85), "tint": (0.16, 0.26),
    },
}


def _preset(severity: str) -> dict:
    if severity not in _PRESETS:
        raise ValueError(f"unknown severity {severity!r}; expected one of {sorted(_PRESETS)}")
    return _PRESETS[severity]


def _fog_veil(img: np.ndarray, coef: float, veil: int) -> np.ndarray:
    """Blend the image toward a uniform light-grey veil (achromatic → colour-safe)."""
    layer = np.full_like(img, veil)
    return cv2.addWeighted(img, 1.0 - coef, layer, coef, 0.0)


def _fog(img, severity, rng):
    coef = float(rng.uniform(*_preset(severity)["fog"]))
    out = _fog_veil(img, coef, veil=220)
    k = int(coef * 7)  # heavier fog softens detail (real fog blurs distant lamps)
    k = k + 1 if k % 2 == 0 else k
    return cv2.GaussianBlur(out, (k, k), 0) if k >= 3 else out


def _haze(img, severity, rng):
    # Haze is a thinner, slightly brighter veil than fog.
    return _fog_veil(img, float(rng.uniform(*_preset(severity)["haze"])), veil=235)


def _rain(img, severity, rng):
    p = _preset(severity)
    h, w = img.shape[:2]
    layer = np.zeros((h, w), np.uint8)
    n = int(h * w * 0.0007 * float(rng.uniform(0.6, 1.3)))
    length = int(rng.integers(*p["rain_len"]))
    slant = int(rng.integers(-8, 9))
    xs = rng.integers(0, w, n)
    ys = rng.integers(0, max(1, h - length), n)
    for x, y in zip(xs.tolist(), ys.tolist(), strict=False):
        cv2.line(layer, (x, y), (x + slant, y + length), 180, 1)
    layer = cv2.blur(layer, (3, 3))
    rain_bgr = cv2.cvtColor(layer, cv2.COLOR_GRAY2BGR)
    out = cv2.addWeighted(img, float(p["rain_bright"]), rain_bgr, 0.7, 0.0)
    return out


def _snow(img, severity, rng):
    p = _preset(severity)
    h, w = img.shape[:2]
    out = cv2.convertScaleAbs(img, alpha=1.0, beta=float(rng.uniform(8, 28)))  # brighten
    n = int(h * w * 0.045 * float(rng.uniform(*p["snow"])))
    xs = rng.integers(0, w, n)
    ys = rng.integers(0, h, n)
    layer = np.zeros((h, w), np.uint8)
    layer[ys, xs] = 255
    layer = cv2.dilate(layer, np.ones((2, 2), np.uint8))  # fatten flakes so they read on screen
    layer = cv2.blur(layer, (2, 2))
    return cv2.addWeighted(out, 1.0, cv2.cvtColor(layer, cv2.COLOR_GRAY2BGR), 0.9, 0.0)


def _sunflare(img, severity, rng):
    p = _preset(severity)
    h, w = img.shape[:2]
    cx = int(float(rng.uniform(0.5, 1.0)) * w)
    cy = int(float(rng.uniform(0.0, 0.3)) * h)  # sun above the runway horizon
    radius = float(rng.uniform(0.20, 0.40)) * min(h, w)
    strength = float(rng.uniform(*p["flare"]))
    yy, xx = np.ogrid[:h, :w]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    glow = np.clip(1.0 - dist / (radius * 2.5), 0.0, 1.0)[..., None]
    out = np.clip(img.astype(np.float32) + glow * 255.0 * strength, 0, 255).astype(np.uint8)
    return out


def _shadow(img, severity, rng):
    p = _preset(severity)
    h, w = img.shape[:2]
    intensity = float(rng.uniform(*p["shadow"]))
    mask = np.zeros((h, w), np.uint8)
    pts = np.array(
        [[int(rng.integers(0, w)), int(rng.integers(h // 3, h))] for _ in range(4)], np.int32
    )
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.blur(mask, (31, 31))
    m = (mask.astype(np.float32) / 255.0 * intensity)[..., None]
    return (img.astype(np.float32) * (1.0 - m)).astype(np.uint8)


def _colour_temp(img, severity, rng, warm: bool):
    """Mild colour-TEMPERATURE shift (white-balance) for time-of-day / season variety.

    Scales the blue/red channels in opposite directions — a warm (golden-hour / autumn) or cool
    (overcast / winter / blue-hour) cast. Deliberately a *balance* shift, not hue/saturation jitter:
    it tints the whole scene but keeps red clearly red and white clearly white, so it never
    relabels the colour-is-the-class lamps (unlike hsv_h/hsv_s, which stay pinned at 0). Mild by
    design — the presets top out around ±0.26 channel gain.
    """
    f = float(rng.uniform(*_preset(severity)["tint"]))
    out = img.astype(np.float32)
    hot, cold = (1.0 + f, 1.0 - 0.7 * f) if warm else (1.0 - 0.7 * f, 1.0 + f)
    out[..., 2] *= hot   # BGR: index 2 = Red
    out[..., 0] *= cold  # index 0 = Blue
    return np.clip(out, 0, 255).astype(np.uint8)


def _warm(img, severity, rng):
    return _colour_temp(img, severity, rng, warm=True)


def _cool(img, severity, rng):
    return _colour_temp(img, severity, rng, warm=False)


_EFFECTS = {
    "rain": _rain, "fog": _fog, "haze": _haze,
    "snow": _snow, "sunflare": _sunflare, "shadow": _shadow,
    "warm": _warm, "cool": _cool,
}


def apply_weather(img_bgr: np.ndarray, condition: str, severity: str = "medium", rng=None) -> np.ndarray:
    """Apply one named weather condition to a BGR uint8 image; returns a fresh contiguous array.

    ``rng`` is a ``numpy.random.Generator`` (pass a seeded one for reproducible/temporally-coherent
    output); defaults to a fresh generator. ``clear`` returns the image unchanged.
    """
    if condition == "clear":
        return img_bgr
    if condition not in _EFFECTS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {sorted(CONDITIONS)}")
    if rng is None:
        rng = np.random.default_rng()
    return np.ascontiguousarray(_EFFECTS[condition](img_bgr, severity, rng))


def random_weather(img_bgr: np.ndarray, severity: str = "medium", p: float = 0.35, rng=None) -> np.ndarray:
    """With probability ``p`` apply one random weather effect; otherwise return the image unchanged."""
    if rng is None:
        rng = np.random.default_rng()
    if float(rng.random()) >= p:
        return img_bgr
    return apply_weather(img_bgr, str(rng.choice(_WEATHER)), severity, rng)


class WeatherAug:
    """Picklable Ultralytics transform that applies OpenCV weather to ``labels['img']`` — WORKER-SAFE.

    Inserted into the training Compose by :func:`install_weather_transform`, so it pickles to spawned
    dataloader workers (unlike a class-method monkeypatch, which lives only in the main process and
    forces ``workers=0``). Worker-side parallelism is what makes mosaic + weather stable: the
    workers=0 main-process path re-triggers the async CUDA race once mosaic's heavy load perturbs
    timing. Each process lazily builds its own seeded RNG (kept ``None`` until first use so the object
    pickles cleanly).
    """

    def __init__(self, severity: str = "medium", prob: float = 0.35, seed: int = 0):
        self.severity = severity
        self.prob = prob
        self.seed = seed
        self._rng = None

    def __call__(self, labels):
        img = labels.get("img")
        if isinstance(img, np.ndarray) and img.ndim == 3 and img.shape[2] == 3:
            if self._rng is None:
                self._rng = np.random.default_rng(self.seed)
            labels["img"] = np.ascontiguousarray(random_weather(img, self.severity, self.prob, self._rng))
        return labels


def install_weather_transform(severity: str = "medium", prob: float = 0.35, seed: int = 0) -> None:
    """Append a :class:`WeatherAug` to Ultralytics' training pipeline (worker-safe; allows workers>0).

    Patches ``v8_transforms`` (called once, in the MAIN process, when the dataset is built) to append
    a picklable WeatherAug just before Format. The built Compose is part of the dataset object, so it
    pickles to spawned workers — weather then runs in parallel worker processes, which (unlike
    workers=0) does NOT perturb main-process timing into the async CUDA race when combined with
    mosaic. Workers import ``weather_aug.WeatherAug``; train_detector_model.py puts this directory on
    sys.path at module import so spawned workers can resolve it.
    """
    import ultralytics.data.augment as aug
    import ultralytics.data.dataset as ds

    orig = aug.v8_transforms

    def patched(dataset, imgsz, hyp, stretch=False):
        compose = orig(dataset, imgsz, hyp, stretch)
        compose.append(WeatherAug(severity, prob, seed))
        return compose

    aug.v8_transforms = patched
    ds.v8_transforms = patched  # the dataset module imported the name directly


def install_training_hook(severity: str = "medium", prob: float = 0.35, seed: int = 0) -> None:
    """DEPRECATED main-process-only fallback (forces ``workers=0``). Prefer install_weather_transform.

    Overrides ``Albumentations.__call__`` with random_weather; only affects the main process, so a
    spawned dataloader worker would not see it. Kept as an escape hatch for debugging.
    """
    import ultralytics.data.augment as aug

    rng = np.random.default_rng(seed)

    def _call(self, labels):
        img = labels.get("img")
        if isinstance(img, np.ndarray) and img.ndim == 3 and img.shape[2] == 3:
            labels["img"] = np.ascontiguousarray(random_weather(img, severity, prob, rng))
        return labels

    aug.Albumentations.__call__ = _call
