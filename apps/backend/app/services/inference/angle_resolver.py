"""Elevation-angle resolution for the inference service.

Wraps the geometry in ``app.services.angle`` with the telemetry source-priority
(file > manual fix > embedded EXIF), the single representative angle for an image,
and the per-frame angle track for a video. Pure functions over the telemetry +
runway id, so ``InferenceService`` keeps thin wrappers and the angle behaviour can
be unit-tested without loading YOLO.
"""

from pathlib import Path

from app.services.angle import (
    compute_elevation_angles,
    extract_gps_pose,
    unavailable_angle,
)
from app.services.state import lamp_index_by_track
from app.services.telemetry import DroneSample, resample_to_frames
from app.validation.schemas import AngleResult, AngleSample, FrameLampState

# Cap the per-frame angle track surfaced to the client. The exact red<->white
# crossing is carried separately by transitions[] (full frame resolution), so the
# track only needs enough points to draw a smooth sweep; evenly downsampling a long
# clip keeps the payload lean. Demo videos are usually well under this.
MAX_ANGLE_TRACK_POINTS = 240


def resolve_drone_samples(
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
    # One head read for BOTH the pose and the RTK std (audit REFACTOR-1): the file carries
    # a 1-sigma band only when it has RTK XMP std; manual + telemetry-file fixes have none.
    embedded = extract_gps_pose(media_path)
    if embedded is not None:
        lat, lon, alt, sigma_h, sigma_v = embedded
        return [
            DroneSample(lat, lon, alt, sigma_horizontal_m=sigma_h, sigma_vertical_m=sigma_v)
        ], "file_metadata"
    return None, None


def angle_from_samples(
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
        rep.latitude,
        rep.longitude,
        rep.altitude_m,
        runway_id,
        angle_source=angle_source or "metadata",
        sigma_horizontal_m=rep.sigma_horizontal_m,
        sigma_vertical_m=rep.sigma_vertical_m,
    )


def angle_for_media(
    media_path: Path,
    runway_id: str,
    drone_metadata: tuple[float, float, float] | None,
    drone_samples: list[DroneSample] | None = None,
) -> AngleResult:
    """Single-fix elevation angle for an image (or any non-tracked media)."""
    samples, source = resolve_drone_samples(media_path, drone_metadata, drone_samples)
    return angle_from_samples(samples, source, runway_id)


def build_angle_track(
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
    evenly downsampled to ``MAX_ANGLE_TRACK_POINTS``; the full-resolution
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
    frame_lamps: dict[int, dict[int, tuple[str, float, float | None]]] = {}
    for track_id, observations in track_observations.items():
        lamp_index = index_by_track.get(track_id)
        if lamp_index is None:
            continue
        # Tuples are (frame, color, center_x, conf[, redness]); tolerate the older
        # 4-tuple shape so nothing breaks if an upstream path doesn't carry redness.
        for frame_idx, color, _center_x, conf, *rest in observations:
            redness = rest[0] if rest else None
            frame_lamps.setdefault(frame_idx, {})[lamp_index] = (color, float(conf), redness)

    kept = evenly_spaced(sorted(frame_angles), MAX_ANGLE_TRACK_POINTS)
    track = [
        AngleSample(
            frame_index=frame_index,
            elevation_angle_deg=frame_angles[frame_index],
            lamps=[
                FrameLampState(index=idx, state=state, confidence=round(conf, 4), redness=redness)
                for idx, (state, conf, redness) in sorted(frame_lamps.get(frame_index, {}).items())
            ],
        )
        for frame_index in kept
    ]
    return track, frame_angles


def evenly_spaced(items: list[int], cap: int) -> list[int]:
    """Down-sample a sorted list to at most ``cap`` evenly-spaced entries (endpoints kept)."""
    if cap <= 1 or len(items) <= cap:
        return items[:1] if cap == 1 else items
    step = (len(items) - 1) / (cap - 1)
    return [items[index] for index in sorted({round(i * step) for i in range(cap)})]
