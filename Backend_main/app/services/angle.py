import math
from pathlib import Path
from typing import Any

from app.validation.schemas import AnglePerLight, AngleResult
from app.services.runways import get_runway


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def compute_elevation_angles(
    drone_latitude: float,
    drone_longitude: float,
    drone_altitude_m: float,
    runway_id: str,
    angle_source: str = "metadata",
) -> AngleResult:
    runway = get_runway(runway_id)
    per_light = []
    for light in runway["lights"]:
        distance_m = haversine(
            drone_latitude,
            drone_longitude,
            light["latitude"],
            light["longitude"],
        )
        height_delta_m = drone_altitude_m - light["altitude_m"]
        angle_deg = math.degrees(math.atan2(height_delta_m, distance_m)) if distance_m else 0.0
        per_light.append(
            AnglePerLight(
                runway_lamp=light["point"],
                distance_m=round(distance_m, 3),
                elevation_angle_deg=round(angle_deg, 6),
            )
        )

    avg_angle = sum(item.elevation_angle_deg for item in per_light) / len(per_light)
    return AngleResult(
        angle_available=True,
        elevation_angle_deg=round(avg_angle, 6),
        per_light_angles=per_light,
        angle_source=angle_source,
        angle_note="Calculated from drone GPS/altitude metadata and seeded PAPI coordinates.",
    )


def unavailable_angle(reason: str) -> AngleResult:
    return AngleResult(
        angle_available=False,
        elevation_angle_deg=None,
        per_light_angles=[],
        angle_source=None,
        angle_note=reason,
    )


def _ratio_to_float(value: Any) -> float | None:
    try:
        if hasattr(value, "values"):
            value = value.values
        if hasattr(value, "num") and hasattr(value, "den"):
            return float(value.num) / float(value.den)
        if isinstance(value, (list, tuple)):
            first = value[0]
            if hasattr(first, "num") and hasattr(first, "den"):
                return float(first.num) / float(first.den)
            return float(first)
        return float(value)
    except Exception:
        return None


def _gps_to_degrees(value: Any) -> float | None:
    try:
        degrees, minutes, seconds = value.values
        return (
            float(degrees.num / degrees.den)
            + float(minutes.num / minutes.den) / 60
            + float(seconds.num / seconds.den) / 3600
        )
    except Exception:
        return None


def extract_gps_metadata(media_path: Path) -> tuple[float, float, float] | None:
    try:
        import exifread
    except ImportError:
        return None

    try:
        with media_path.open("rb") as file:
            tags = exifread.process_file(file, details=False)
    except Exception:
        return None

    lat_ref = tags.get("GPS GPSLatitudeRef")
    lat_value = tags.get("GPS GPSLatitude")
    lon_ref = tags.get("GPS GPSLongitudeRef")
    lon_value = tags.get("GPS GPSLongitude")
    alt_ref = tags.get("GPS GPSAltitudeRef")
    alt_value = tags.get("GPS GPSAltitude")

    if not lat_value or not lon_value or not alt_value:
        return None

    latitude = _gps_to_degrees(lat_value)
    longitude = _gps_to_degrees(lon_value)
    altitude = _ratio_to_float(alt_value)
    if latitude is None or longitude is None or altitude is None:
        return None

    if lat_ref and getattr(lat_ref, "values", "N") != "N":
        latitude = -latitude
    if lon_ref and getattr(lon_ref, "values", "E") != "E":
        longitude = -longitude
    if alt_ref and getattr(alt_ref, "values", 0) == 1:
        altitude = -altitude

    return latitude, longitude, altitude
