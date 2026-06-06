"""Shared telemetry primitives: the :class:`DroneSample` fix, the error type, and
the numeric coercion/range helpers every parser uses.

Intentionally free of any geometry/inference imports so the parsers can be unit-tested
in isolation and reused by the offline pipeline if needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.validation.analyze import (
    ALTITUDE_MAX_M,
    ALTITUDE_MIN_M,
    LATITUDE_MAX_DEG,
    LATITUDE_MIN_DEG,
    LONGITUDE_MAX_DEG,
    LONGITUDE_MIN_DEG,
)


@dataclass(frozen=True)
class DroneSample:
    """One telemetry fix: WGS-84 position + ellipsoidal altitude.

    ``frame_index`` (0-based) and ``time_s`` (seconds from the clip start) are
    preserved when the source provides them (DJI SRT counter / timestamp, or a CSV
    frame column) so video frames can be aligned to the right fix; both are
    ``None`` for a bare position file.
    """

    latitude: float
    longitude: float
    altitude_m: float
    frame_index: int | None = None
    time_s: float | None = None
    # RTK 1-sigma position std (m), carried only for fixes that have it (the embedded
    # DJI-XMP path). Horizontal combines lat/lon; vertical is height. Used to put a
    # 1-sigma band on the elevation angle; ``None`` for manual + telemetry-file fixes.
    sigma_horizontal_m: float | None = None
    sigma_vertical_m: float | None = None


class TelemetryError(ValueError):
    """Raised when a telemetry file cannot be parsed into any usable sample.

    A ``ValueError`` subclass so the analyze endpoints' existing ``except
    ValueError -> HTTP 400`` mapping turns it into a clean client error.
    """


# Hard cap on parsed telemetry fixes. A real DJI descent track is hundreds to a few
# thousand cues; anything far above this is pathological (or hostile) input, so we
# bound it to keep both memory and the per-frame resample (O(frame_count x n_samples))
# in check (audit: telemetry sample-count DoS).
MAX_TELEMETRY_SAMPLES = 50_000


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    # Guard against NaN/inf flowing into the angle math.
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _coerce_frame_index(value: object) -> int | None:
    out = _coerce_float(value)
    if out is None or out < 0 or not out.is_integer():
        return None
    return int(out)


def _in_range(lat: float, lon: float, alt: float) -> bool:
    return (
        LATITUDE_MIN_DEG <= lat <= LATITUDE_MAX_DEG
        and LONGITUDE_MIN_DEG <= lon <= LONGITUDE_MAX_DEG
        and ALTITUDE_MIN_M <= alt <= ALTITUDE_MAX_M
    )


def _make_sample(
    lat: float | None,
    lon: float | None,
    alt: float | None,
    *,
    frame_index: int | None = None,
    time_s: float | None = None,
) -> DroneSample | None:
    """Build a range-validated sample, or ``None`` if any field is missing/garbage.

    Out-of-range fixes are dropped (not raised) so one corrupt row in an otherwise
    good track doesn't fail the whole upload; the caller raises only when *no*
    sample survives.
    """
    if lat is None or lon is None or alt is None:
        return None
    if not _in_range(lat, lon, alt):
        return None
    return DroneSample(
        latitude=lat, longitude=lon, altitude_m=alt, frame_index=frame_index, time_s=time_s
    )
