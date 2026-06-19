"""DJI ``.SRT`` per-frame subtitle telemetry parser.

Handles both the modern bracketed layout (``[latitude: ...]``) and the older
``GPS(longitude,latitude,...)`` layout. ``rel_alt`` is deliberately never read as
altitude — only absolute (WGS-84) heights feed the angle calc.
"""

from __future__ import annotations

import re

from app.services.telemetry.sample import (
    DroneSample,
    _capped_indices,
    _coerce_float,
    _make_sample,
)

_NUMBER = r"[+-]?\d+(?:\.\d+)?"

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

# Cheap cue-HEADER counter (no body capture, no DOTALL) used only to size the cap
# before building samples. Re-running the full body-capturing _SRT_CUE_RE just to
# count would scan every (potentially huge) body twice — doubling worst-case CPU on a
# hostile file. This matches the same counter+timecode header _SRT_CUE_RE starts each
# cue with, so the count aligns for well-formed input (audit 2026-06-19).
_SRT_CUE_HEAD_RE = re.compile(
    r"\d{1,9}\s*\n\s*\d{2}:\d{2}:\d{2}[.,]\d{1,3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{1,3}"
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
    # Bound memory like the CSV/JSON parsers (audit #14 parity): count the cues in a
    # cheap first pass (match objects are transient/GC'd), then build DroneSamples only
    # for a uniformly-strided subset. Without this a pathological SRT of millions of
    # minimal cues allocates every sample before the post-parse cap in __init__ runs.
    total = sum(1 for _ in _SRT_CUE_HEAD_RE.finditer(text))
    keep = frozenset(_capped_indices(total))
    for order, cue in enumerate(_SRT_CUE_RE.finditer(text)):
        if order not in keep:
            continue
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
