"""Per-image metadata extraction from EXIF + DJI XMP.

We avoid loading the full JPEG pixel buffer; only the first ~80 KB is read because the XMP
packet sits early in the file. EXIF tags are pulled with PIL because PIL only parses headers.

Field names and value formats verified against:
- WideCamera sample: PROJECT1-PAPI/DJI_202604281910_010_UgCS/DJI_20260428192656_0001_V.JPG
- ZoomCamera sample: PROJECT1-PAPI/DJI_202604291300_032_day2700mdwnzoom/DJI_20260429135036_0001_V.JPG
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

XMP_PROBE_BYTES = 96 * 1024  # XMP packet on DJI M4E lives in the first ~80 KB

# Regex matches `drone-dji:FieldName="value"` even when XMP uses single quotes, surrounding
# whitespace, or unusual namespace prefixes (we strictly look for `drone-dji:`).
_XMP_VALUE_RE = re.compile(
    rb'drone-dji:(?P<field>[A-Za-z0-9]+)\s*=\s*["\'](?P<val>[^"\']*)["\']'
)

# EXIF tag-name -> tag-id (built once)
_EXIF_TAG_IDS = {name: tag_id for tag_id, name in ExifTags.TAGS.items()}
_GPS_TAG_IDS = {name: tag_id for tag_id, name in ExifTags.GPSTAGS.items()}


def _read_head(path: Path) -> bytes:
    with path.open("rb") as fh:
        return fh.read(XMP_PROBE_BYTES)


def _parse_xmp(buf: bytes) -> dict[str, str]:
    """Return all `drone-dji:Field="val"` pairs found in the head buffer."""
    out: dict[str, str] = {}
    for m in _XMP_VALUE_RE.finditer(buf):
        out[m.group("field").decode("ascii")] = m.group("val").decode("ascii", errors="replace")
    return out


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(float(val))  # tolerate '50.0' etc.
    except (TypeError, ValueError):
        return None


def _dms_to_dd(dms: tuple, ref: str) -> float | None:
    """Convert EXIF GPS DMS triple + N/S/E/W ref to signed decimal degrees."""
    if dms is None:
        return None
    try:
        deg = float(dms[0])
        minutes = float(dms[1])
        seconds = float(dms[2])
    except (TypeError, ValueError, IndexError):
        return None
    dd = deg + minutes / 60.0 + seconds / 3600.0
    if ref in ("S", "W"):
        dd = -dd
    return dd


def _extract_exif(path: Path) -> dict[str, Any]:
    """Pull a small set of EXIF tags using PIL (no pixel decode)."""
    out: dict[str, Any] = {}
    try:
        with Image.open(path) as img:
            exif = img._getexif() or {}
    except Exception:
        return out

    def _exif(name: str) -> Any:
        return exif.get(_EXIF_TAG_IDS.get(name)) if name in _EXIF_TAG_IDS else None

    out["image_width"] = _exif("ExifImageWidth")
    out["image_height"] = _exif("ExifImageHeight")
    out["focal_35mm"] = _exif("FocalLengthIn35mmFilm")
    out["iso"] = _exif("ISOSpeedRatings")
    expo = _exif("ExposureTime")
    out["exposure_s"] = str(expo) if expo is not None else None
    fn = _exif("FNumber")
    out["f_number"] = float(fn) if fn is not None else None
    out["local_datetime"] = _exif("DateTime")

    gps_info = _exif("GPSInfo") or {}
    if gps_info:
        lat_dms = gps_info.get(_GPS_TAG_IDS.get("GPSLatitude"))
        lat_ref = gps_info.get(_GPS_TAG_IDS.get("GPSLatitudeRef"))
        lon_dms = gps_info.get(_GPS_TAG_IDS.get("GPSLongitude"))
        lon_ref = gps_info.get(_GPS_TAG_IDS.get("GPSLongitudeRef"))
        out["exif_lat"] = _dms_to_dd(lat_dms, lat_ref) if lat_ref else None
        out["exif_lon"] = _dms_to_dd(lon_dms, lon_ref) if lon_ref else None
    else:
        out["exif_lat"] = None
        out["exif_lon"] = None

    return out


def extract_image_metadata(path: Path) -> dict[str, Any]:
    """Extract the full per-image metadata row described in PROMPT phase 2.

    DJI XMP is the authoritative source for lat/lon when present (RTK-corrected). We fall back
    to EXIF GPSInfo if XMP is missing the field for some reason.
    """
    head = _read_head(path)
    xmp = _parse_xmp(head)
    exif = _extract_exif(path)

    # Prefer XMP-RTK lat/lon; fall back to EXIF GPS.
    lat = _to_float(xmp.get("GpsLatitude")) if xmp.get("GpsLatitude") else exif["exif_lat"]
    lon = _to_float(xmp.get("GpsLongitude")) if xmp.get("GpsLongitude") else exif["exif_lon"]

    return {
        "folder": path.parent.name,
        "file": path.name,
        "lat": lat,
        "lon": lon,
        "alt_ellipsoidal_m": _to_float(xmp.get("AbsoluteAltitude")),
        "agl_m": _to_float(xmp.get("RelativeAltitude")),
        "gimbal_yaw_deg": _to_float(xmp.get("GimbalYawDegree")),
        "gimbal_pitch_deg": _to_float(xmp.get("GimbalPitchDegree")),
        "gimbal_roll_deg": _to_float(xmp.get("GimbalRollDegree")),
        "flight_yaw_deg": _to_float(xmp.get("FlightYawDegree")),
        "flight_pitch_deg": _to_float(xmp.get("FlightPitchDegree")),
        "flight_roll_deg": _to_float(xmp.get("FlightRollDegree")),
        "speed_x_mps": _to_float(xmp.get("FlightXSpeed")),
        "speed_y_mps": _to_float(xmp.get("FlightYSpeed")),
        "speed_z_mps": _to_float(xmp.get("FlightZSpeed")),
        "rtk_flag": _to_int(xmp.get("RtkFlag")),
        "rtk_std_lat_m": _to_float(xmp.get("RtkStdLat")),
        "rtk_std_lon_m": _to_float(xmp.get("RtkStdLon")),
        "rtk_std_hgt_m": _to_float(xmp.get("RtkStdHgt")),
        "camera": xmp.get("ImageSource"),
        "image_width": exif.get("image_width"),
        "image_height": exif.get("image_height"),
        "focal_35mm": exif.get("focal_35mm"),
        "iso": exif.get("iso"),
        "exposure_s": exif.get("exposure_s"),
        "f_number": exif.get("f_number"),
        "utc_exposure": xmp.get("UTCAtExposure"),
        "local_datetime": exif.get("local_datetime"),
        "lrf_status": xmp.get("LRFStatus"),
        "lrf_target_distance_m": _to_float(xmp.get("LRFTargetDistance")),
        "lrf_target_lat": _to_float(xmp.get("LRFTargetLat")),
        "lrf_target_lon": _to_float(xmp.get("LRFTargetLon")),
        "lrf_target_alt_m": _to_float(xmp.get("LRFTargetAlt")),  # NOTE: relative to camera (not WGS84 absolute)
        "lrf_target_abs_alt_m": _to_float(xmp.get("LRFTargetAbsAlt")),  # WGS84 absolute
        "sensor_temperature_c": _to_float(xmp.get("SensorTemperature")),
    }
