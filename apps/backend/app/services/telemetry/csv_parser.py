"""CSV telemetry parser: ``latitude,longitude,altitude`` rows.

Header optional (common column aliases recognised); only ABSOLUTE altitude columns
are accepted so a relative/AGL column can't be mistaken for the WGS-84 height the
angle calc needs. Named ``csv_parser`` (not ``csv``) so it does not shadow the
stdlib :mod:`csv` it imports.
"""

from __future__ import annotations

import csv
import io

from app.services.telemetry.sample import (
    DroneSample,
    _coerce_float,
    _coerce_frame_index,
    _make_sample,
)

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
