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

This module is intentionally free of any geometry/inference imports so it can be
unit-tested in isolation and reused by the offline pipeline if needed.
"""

from __future__ import annotations

import csv
import io
import json
import re
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


# --- numeric helpers ---------------------------------------------------------

_NUMBER = r"[+-]?\d+(?:\.\d+)?"

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


# --- DJI SRT -----------------------------------------------------------------

# One SRT cue: an integer counter, a "start --> end" timecode line, then the body
# (which may itself span several lines) up to the next counter+timecode or EOF.
# Comma OR dot millisecond separators are tolerated (DJI uses ',').
_SRT_CUE_RE = re.compile(
    r"(?P<counter>\d{1,9})\s*\n"
    r"\s*(?P<start>\d{2}:\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{1,3}"
    r"(?P<body>.*?)"
    r"(?=\n\s*\d{1,9}\s*\n\s*\d{2}:\d{2}:\d{2}[.,]\d{1,3}\s*-->|\Z)",
    re.DOTALL,
)

# Bracketed modern DJI fields, e.g. "[latitude: 47.67]" / "[abs_alt : 520.0]".
# The key may use ':' or '=', with or without surrounding spaces; the value is the
# first number that follows. ``rel_alt`` is deliberately NOT matched as altitude.
_SRT_LAT_RE = re.compile(rf"\blatitude\s*[:=]\s*(?P<v>{_NUMBER})", re.IGNORECASE)
_SRT_LON_RE = re.compile(rf"\blongitude\s*[:=]\s*(?P<v>{_NUMBER})", re.IGNORECASE)
_SRT_ABS_ALT_RE = re.compile(rf"\babs_alt\s*[:=]\s*(?P<v>{_NUMBER})", re.IGNORECASE)
# A bare "altitude" (some firmwares) — absolute. Negative lookbehind keeps it from
# matching the "_alt" tail of rel_alt/abs_alt.
_SRT_ALT_RE = re.compile(rf"(?<![a-z_])altitude\s*[:=]\s*(?P<v>{_NUMBER})", re.IGNORECASE)
# Older layout: "GPS(longitude,latitude,xxx)" — note DJI writes LON first. The 3rd
# field is satellite count on most firmwares (NOT altitude), so it is ignored.
_SRT_GPS_RE = re.compile(
    rf"GPS\(\s*(?P<lon>{_NUMBER})\s*,\s*(?P<lat>{_NUMBER})\s*,\s*{_NUMBER}\s*\)",
    re.IGNORECASE,
)


def _srt_time_to_seconds(stamp: str) -> float | None:
    match = re.match(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{1,3})", stamp)
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis.ljust(3, "0")) / 1000.0


def _parse_srt(text: str) -> list[DroneSample]:
    samples: list[DroneSample] = []
    for order, cue in enumerate(_SRT_CUE_RE.finditer(text)):
        body = cue.group("body")
        lat = lon = alt = None

        lat_match = _SRT_LAT_RE.search(body)
        lon_match = _SRT_LON_RE.search(body)
        if lat_match and lon_match:
            lat = _coerce_float(lat_match.group("v"))
            lon = _coerce_float(lon_match.group("v"))
        else:
            gps = _SRT_GPS_RE.search(body)
            if gps:
                lat = _coerce_float(gps.group("lat"))
                lon = _coerce_float(gps.group("lon"))

        abs_match = _SRT_ABS_ALT_RE.search(body) or _SRT_ALT_RE.search(body)
        if abs_match:
            alt = _coerce_float(abs_match.group("v"))

        # DJI's per-cue counter is the 1-based frame number; store it 0-based so it
        # lines up with the inference loop's frame_index. Fall back to scan order.
        counter = _coerce_float(cue.group("counter"))
        frame_index = int(counter) - 1 if counter is not None and counter >= 1 else order
        time_s = _srt_time_to_seconds(cue.group("start"))

        sample = _make_sample(lat, lon, alt, frame_index=frame_index, time_s=time_s)
        if sample is not None:
            samples.append(sample)
    return samples


# --- CSV ---------------------------------------------------------------------

_CSV_ALIASES: dict[str, tuple[str, ...]] = {
    "lat": ("latitude", "lat", "gpslatitude", "drone_latitude"),
    "lon": ("longitude", "lon", "lng", "long", "gpslongitude", "drone_longitude"),
    # Absolute altitude only — rel_alt / agl / height-above-takeoff are excluded so
    # a relative column can't be mistaken for the WGS-84 height the angle needs.
    "alt": (
        "altitude_m",
        "altitude",
        "abs_alt",
        "absolute_altitude",
        "alt_ellipsoidal_m",
        "ellipsoidal_altitude",
        "drone_altitude_m",
        "alt",
    ),
    "frame": ("frame", "frame_index", "frameidx", "index"),
    "time": ("time_s", "time", "timestamp", "t"),
}


def _resolve_columns(header: list[str]) -> dict[str, int]:
    lowered = [h.strip().lower() for h in header]
    resolved: dict[str, int] = {}
    for key, aliases in _CSV_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                resolved[key] = lowered.index(alias)
                break
    return resolved


def _looks_like_header(row: list[str]) -> bool:
    # A header has no field that parses as a number (telemetry rows are all numeric).
    return all(_coerce_float(cell) is None for cell in row) and len(row) >= 2


def _parse_csv(text: str) -> list[DroneSample]:
    # Sniff the delimiter (comma / semicolon / tab) from the first non-empty line.
    sample_text = "\n".join(line for line in text.splitlines() if line.strip())[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    try:
        rows = [
            row
            for row in csv.reader(io.StringIO(text), delimiter=delimiter)
            if any(c.strip() for c in row)
        ]
    except csv.Error:
        # A malformed CSV (e.g. a field above csv's 128 KB field-size limit) raises
        # csv.Error, which is not a ValueError; degrade to the "no usable fixes" path
        # so the endpoint returns a clean 400 instead of a leaked 500 (audit).
        return []
    if not rows:
        return []

    if _looks_like_header(rows[0]):
        cols = _resolve_columns(rows[0])
        data_rows = rows[1:]
        if not all(k in cols for k in ("lat", "lon", "alt")):
            # Headed file but without the required columns — unusable.
            return []
        lat_i, lon_i, alt_i = cols["lat"], cols["lon"], cols["alt"]
        frame_i, time_i = cols.get("frame"), cols.get("time")
    else:
        # Headerless: assume the conventional latitude, longitude, altitude order.
        cols = {}
        data_rows = rows
        lat_i, lon_i, alt_i = 0, 1, 2
        frame_i = time_i = None

    samples: list[DroneSample] = []
    for order, row in enumerate(data_rows):
        biggest = max(i for i in (lat_i, lon_i, alt_i) if i is not None)
        if len(row) <= biggest:
            continue
        lat = _coerce_float(row[lat_i])
        lon = _coerce_float(row[lon_i])
        alt = _coerce_float(row[alt_i])
        if frame_i is None:
            frame_index = order
        elif len(row) > frame_i:
            frame_index = _coerce_frame_index(row[frame_i])
            if frame_index is None:
                continue
        else:
            continue
        time_s = _coerce_float(row[time_i]) if time_i is not None and len(row) > time_i else None
        sample = _make_sample(lat, lon, alt, frame_index=frame_index, time_s=time_s)
        if sample is not None:
            samples.append(sample)
    return samples


# --- JSON --------------------------------------------------------------------

_JSON_LAT_KEYS = ("latitude", "lat", "drone_latitude")
_JSON_LON_KEYS = ("longitude", "lon", "lng", "long", "drone_longitude")
_JSON_ALT_KEYS = (
    "altitude_m",
    "altitude",
    "abs_alt",
    "absolute_altitude",
    "alt_ellipsoidal_m",
    "drone_altitude_m",
    "alt",
)
_JSON_FRAME_KEYS = ("frame_index", "frame", "index")
_JSON_TIME_KEYS = ("time_s", "time", "timestamp", "t")


def _pick(entry: dict, keys: tuple[str, ...]) -> object | None:
    lowered = {str(k).lower(): v for k, v in entry.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _parse_json(text: str) -> list[DroneSample]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError, RecursionError):
        # RecursionError (deeply-nested array/object) subclasses RuntimeError, not
        # ValueError, so without it here the exception escapes as an unhandled HTTP 500
        # with a stack trace on the unauthenticated analyze path (audit blocker).
        return []

    if isinstance(data, dict):
        for container_key in ("samples", "track", "points", "telemetry", "frames"):
            if isinstance(data.get(container_key), list):
                entries = data[container_key]
                break
        else:
            entries = [data]
    elif isinstance(data, list):
        entries = data
    else:
        return []

    samples: list[DroneSample] = []
    for order, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        lat = _coerce_float(_pick(entry, _JSON_LAT_KEYS))
        lon = _coerce_float(_pick(entry, _JSON_LON_KEYS))
        alt = _coerce_float(_pick(entry, _JSON_ALT_KEYS))
        frame_raw = _pick(entry, _JSON_FRAME_KEYS)
        if frame_raw is None:
            frame_index = order
        else:
            frame_index = _coerce_frame_index(frame_raw)
            if frame_index is None:
                continue
        time_s = _coerce_float(_pick(entry, _JSON_TIME_KEYS))
        sample = _make_sample(lat, lon, alt, frame_index=frame_index, time_s=time_s)
        if sample is not None:
            samples.append(sample)
    return samples


# --- public entry point ------------------------------------------------------


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
            # Nearest frame_index (linear scan is fine for demo-sized tracks).
            best = min(range(len(keys)), key=lambda i: abs(keys[i] - frame))
            out.append(indexed[best])
        return out

    last = len(samples) - 1
    return [samples[round(frame * last / (frame_count - 1))] for frame in range(frame_count)]
