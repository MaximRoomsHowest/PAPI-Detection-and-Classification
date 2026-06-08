"""Drone telemetry-file parsing for the elevation-angle calc.

The Live Demo lets a user upload the drone's telemetry *alongside* the media so
the PAPI elevation angle can be computed even when the footage carries no usable
embedded GPS (DJI **videos** keep their per-frame track in a separate ``.SRT``
sidecar; browser-exported clips/images are often stripped entirely).

Three formats are accepted and auto-detected (by extension, then by sniffing the
bytes):

* **DJI ``.SRT``** — the per-frame subtitle telemetry a DJI drone records next to
  a video. Modern (bracketed) and older ``GPS(...)`` layouts are both handled.
* **CSV** — ``latitude,longitude,altitude`` rows (header optional; common column
  aliases recognised).
* **JSON** — a single ``{lat,lon,alt}`` object or an array / ``{"samples":[...]}``
  of them.

Every parser returns a list of :class:`DroneSample`. A sample needs a latitude, a
longitude, and an **absolute** (WGS-84 / ellipsoidal) altitude — the same datum as
the surveyed lamp coordinates, so the ENU ``Up`` component is a true height
difference. A *relative* altitude (DJI ``rel_alt`` / barometer height above
take-off) cannot be turned into an absolute height here and is therefore ignored;
a file that carries only relative altitude yields no usable samples and is
rejected, rather than silently fabricating an angle off the wrong datum.

This package is split by format (``srt`` / ``csv_parser`` / ``json_parser``) over a
shared ``sample`` core; it is intentionally free of any geometry/inference imports so
it can be unit-tested in isolation and reused by the offline pipeline if needed.
"""

from __future__ import annotations

import bisect
import re

from app.services.telemetry.csv_parser import _parse_csv
from app.services.telemetry.json_parser import _parse_json
from app.services.telemetry.sample import (
    MAX_TELEMETRY_SAMPLES,
    DroneSample,
    TelemetryError,
)
from app.services.telemetry.srt import _parse_srt

__all__ = [
    "DroneSample",
    "TelemetryError",
    "MAX_TELEMETRY_SAMPLES",
    "parse_telemetry",
    "resample_to_frames",
]


def _decode(raw: bytes) -> str:
    # DJI SRT files are UTF-8 (sometimes with a BOM); fall back to latin-1 so an odd
    # byte never aborts parsing.
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="ignore")


def _detect_kind(filename: str, text: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("srt", "csv", "json"):
        return ext
    # No / unknown extension: sniff the content.
    stripped = text.lstrip()
    if stripped[:1] in ("{", "["):
        return "json"
    if "-->" in text and re.search(r"\d{2}:\d{2}:\d{2}[.,]\d", text):
        return "srt"
    return "csv"


def parse_telemetry(filename: str, raw: bytes) -> list[DroneSample]:
    """Parse a telemetry upload into validated :class:`DroneSample` fixes.

    Auto-detects DJI SRT / CSV / JSON from the extension, falling back to a content
    sniff. Raises :class:`TelemetryError` (a ``ValueError``) when the file yields no
    usable sample — empty, malformed, missing lat/lon, or carrying only a relative
    altitude — so the endpoint returns a clear 400 instead of a silent
    angle-unavailable.
    """
    if not raw or not raw.strip():
        raise TelemetryError("The telemetry file is empty.")

    text = _decode(raw)
    kind = _detect_kind(filename or "", text)
    parser = {"srt": _parse_srt, "csv": _parse_csv, "json": _parse_json}[kind]
    samples = parser(text)

    if len(samples) > MAX_TELEMETRY_SAMPLES:
        # Pathologically long track: uniformly downsample to the cap so the per-frame
        # resample stays bounded (audit: sample-count / O(n*m) resample DoS). Uniform
        # striding preserves the track's span rather than truncating the descent.
        stride = len(samples) / MAX_TELEMETRY_SAMPLES
        samples = [samples[int(i * stride)] for i in range(MAX_TELEMETRY_SAMPLES)]

    if not samples:
        raise TelemetryError(
            "No usable drone fixes found in the telemetry file. Expected DJI .SRT, or a "
            "CSV/JSON with latitude, longitude and an absolute (WGS-84) altitude."
        )
    return samples


def resample_to_frames(samples: list[DroneSample], frame_count: int) -> list[DroneSample]:
    """Align a telemetry track to ``frame_count`` video frames (one sample per frame).

    * When the samples carry their own ``frame_index`` (DJI SRT counter), each video
      frame takes the nearest-by-index fix — robust to a frame-count mismatch from
      inference caps or dropped frames.
    * Otherwise the track is mapped proportionally (frame ``f`` -> sample
      ``round(f * (N-1)/(M-1))``), so a short position log still spreads across the clip.

    Returns a list of length ``max(frame_count, 0)``; an empty input yields an empty list.
    """
    if frame_count <= 0 or not samples:
        return []
    if frame_count == 1:
        return [samples[len(samples) // 2]]

    have_indices = all(s.frame_index is not None for s in samples)
    if have_indices:
        indexed = sorted(samples, key=lambda s: s.frame_index)
        keys = [s.frame_index for s in indexed]
        out: list[DroneSample] = []
        for frame in range(frame_count):
            # Nearest frame_index via binary search on the sorted keys — O((F+N)logN)
            # instead of the previous O(F*N) linear scan. Ties resolve to the lower index
            # (matches the old min()'s first-wins behaviour).
            pos = bisect.bisect_left(keys, frame)
            if pos == 0:
                best = 0
            elif pos == len(keys):
                best = len(keys) - 1
            else:
                best = pos if (keys[pos] - frame) < (frame - keys[pos - 1]) else pos - 1
            out.append(indexed[best])
        return out

    last = len(samples) - 1
    return [samples[round(frame * last / (frame_count - 1))] for frame in range(frame_count)]
