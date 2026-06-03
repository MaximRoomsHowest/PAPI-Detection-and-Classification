"""Drone→PAPI elevation-angle geometry.

Implements the **client's** method (see the BigBrain reference diagrams
papi-angle-calculation-example*.png): convert both the drone and the PAPI from
WGS-84 LLA → ECEF → ENU (a local East-North-Up tangent frame at the PAPI), then
the elevation angle is ``alpha = arctan(Up / horizontal)`` where
``horizontal = sqrt(East**2 + North**2)``. The primary angle is taken from the
**PAPI midpoint** (centroid of the lamp row); per-lamp angles are also returned
(each lamp as its own ENU origin).

This supersedes the earlier haversine + raw-altitude-subtraction approximation.
At 300-1000 m baselines the two agree to ~0.01 deg, but ENU is the geodetically
correct transform the client specified and avoids the spherical-earth shortcut.
``haversine`` is retained for distance display / cross-checks.
"""

import math
import re
from pathlib import Path
from typing import Any

from app.services.runways import get_runway
from app.validation.analyze import ALTITUDE_MAX_M
from app.validation.schemas import AnglePerLight, AngleResult

# WGS-84 ellipsoid — the datum the DJI GPS metadata and the surveyed lamp
# coordinates are both expressed in (ellipsoidal height). Keeping drone and lamp
# in the SAME datum is what makes the Up component a true height difference.
_WGS84_A = 6_378_137.0  # semi-major axis (m)
_WGS84_F = 1.0 / 298.257223563  # flattening
_WGS84_E2 = _WGS84_F * (2.0 - _WGS84_F)  # first eccentricity squared

# Past this nearest-lamp horizontal distance the drone is almost certainly not on an
# approach to the selected PAPI. A usable PAPI signal reaches ~5 NM (~9.3 km); this
# leaves margin so a legitimate long final never trips it, while a wrong-runway or
# wrong-datum selection (off by 10x-100x) always does. A SANITY bound for honesty,
# NOT a certification limit — the angle is flagged implausible, never withheld.
PLAUSIBILITY_MAX_NEAREST_LAMP_M = 15_000.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle horizontal distance (m). Retained for display + cross-checks;
    the elevation angle itself now comes from the ENU transform below."""
    radius_m = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def _geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> tuple[float, float, float]:
    """WGS-84 geodetic (lat, lon, ellipsoidal height) → ECEF (X, Y, Z) in metres."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    n = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_m) * cos_lat * math.cos(lon)
    y = (n + alt_m) * cos_lat * math.sin(lon)
    z = (n * (1.0 - _WGS84_E2) + alt_m) * sin_lat
    return x, y, z


def _geodetic_to_enu(
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
    ref_lat_deg: float,
    ref_lon_deg: float,
    ref_alt_m: float,
) -> tuple[float, float, float]:
    """A WGS-84 LLA point → local ENU (East, North, Up) metres at the reference
    origin. This is the LLA→ECEF→ENU chain from the client's reference diagram."""
    x, y, z = _geodetic_to_ecef(lat_deg, lon_deg, alt_m)
    x0, y0, z0 = _geodetic_to_ecef(ref_lat_deg, ref_lon_deg, ref_alt_m)
    dx, dy, dz = x - x0, y - y0, z - z0

    ref_lat = math.radians(ref_lat_deg)
    ref_lon = math.radians(ref_lon_deg)
    sin_lat = math.sin(ref_lat)
    cos_lat = math.cos(ref_lat)
    sin_lon = math.sin(ref_lon)
    cos_lon = math.cos(ref_lon)

    east = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    return east, north, up


def _elevation_from_enu(east: float, north: float, up: float) -> tuple[float, float]:
    """Return (horizontal_distance_m, elevation_angle_deg) from an ENU vector."""
    horizontal = math.hypot(east, north)
    if horizontal == 0.0:
        angle = 90.0 if up > 0 else (-90.0 if up < 0 else 0.0)
    else:
        angle = math.degrees(math.atan2(up, horizontal))
    return horizontal, angle


def _angle_uncertainty_deg(
    horizontal_m: float,
    up_m: float,
    sigma_horizontal_m: float | None,
    sigma_vertical_m: float | None,
) -> float | None:
    """First-order 1-sigma uncertainty (deg) on ``alpha = atan2(up, horizontal)``.

    Propagates the drone-position standard deviations through the elevation-angle
    partials (the surveyed lamp is treated as exact):
        d(alpha)/d(up)         =  horizontal / r^2
        d(alpha)/d(horizontal) = -up / r^2          with r^2 = horizontal^2 + up^2
    ``sigma_vertical`` feeds the up partial, ``sigma_horizontal`` the horizontal one.
    Returns None when no std is supplied or the geometry is degenerate (r == 0), so a
    band is shown only when it is genuinely measured.
    """
    if sigma_horizontal_m is None or sigma_vertical_m is None:
        return None
    r2 = horizontal_m * horizontal_m + up_m * up_m
    if r2 <= 0.0:
        return None
    d_up = horizontal_m / r2
    d_horizontal = -up_m / r2
    sigma_rad = math.hypot(d_up * sigma_vertical_m, d_horizontal * sigma_horizontal_m)
    return round(math.degrees(sigma_rad), 4)


def compute_elevation_angles(
    drone_latitude: float,
    drone_longitude: float,
    drone_altitude_m: float,
    runway_id: str,
    angle_source: str = "metadata",
    sigma_horizontal_m: float | None = None,
    sigma_vertical_m: float | None = None,
) -> AngleResult:
    """Elevation angle(s) from the drone to a PAPI installation via WGS-84 ENU.

    ``elevation_angle_deg`` is the client's primary metric — the angle to the PAPI
    **midpoint** (centroid of the lamp row). ``per_light_angles`` gives one angle
    per lamp (each lamp as its own ENU origin), preserving the existing per-lamp chart.

    When the drone fix carries RTK standard deviations (``sigma_horizontal_m`` /
    ``sigma_vertical_m``), a first-order 1-sigma band is propagated onto the midpoint
    angle. The result is also flagged ``plausible=False`` when the nearest lamp is
    implausibly far away (wrong runway / datum) — the angle is still returned.
    """
    runway = get_runway(runway_id)
    lights = runway["lights"]

    per_light: list[AnglePerLight] = []
    for light in lights:
        east, north, up = _geodetic_to_enu(
            drone_latitude,
            drone_longitude,
            drone_altitude_m,
            light["latitude"],
            light["longitude"],
            light["altitude_m"],
        )
        horizontal, angle_deg = _elevation_from_enu(east, north, up)
        per_light.append(
            AnglePerLight(
                runway_lamp=light["point"],
                distance_m=round(horizontal, 3),
                elevation_angle_deg=round(angle_deg, 6),
            )
        )

    # PAPI midpoint (centroid of the four lamps) — the apex of the angle in the
    # client's diagram. Lamp altitudes are equal, so the mean is the row centre.
    mid_lat = sum(light["latitude"] for light in lights) / len(lights)
    mid_lon = sum(light["longitude"] for light in lights) / len(lights)
    mid_alt = sum(light["altitude_m"] for light in lights) / len(lights)
    east, north, up = _geodetic_to_enu(
        drone_latitude, drone_longitude, drone_altitude_m, mid_lat, mid_lon, mid_alt
    )
    mid_horizontal, midpoint_angle = _elevation_from_enu(east, north, up)

    # Plausibility: the closest lamp's horizontal distance. Past the sanity bound the
    # drone fix and the runway don't belong together (wrong runway / datum) — flag it
    # but still return the geometrically-correct angle so the demo is never blocked.
    nearest_m = min((light.distance_m for light in per_light), default=None)
    plausible = True
    plausibility_note: str | None = None
    if nearest_m is not None and nearest_m > PLAUSIBILITY_MAX_NEAREST_LAMP_M:
        plausible = False
        plausibility_note = (
            f"Drone fix is {nearest_m / 1000:.1f} km from the nearest lamp of "
            f"'{runway_id}', far beyond a usable PAPI approach distance — likely the "
            f"wrong runway was selected or the coordinates use a different datum. The "
            f"angle is geometrically computed but probably not meaningful."
        )

    return AngleResult(
        angle_available=True,
        elevation_angle_deg=round(midpoint_angle, 6),
        per_light_angles=per_light,
        angle_source=angle_source,
        angle_note=(
            "Elevation from the PAPI midpoint via a WGS-84 LLA->ECEF->ENU transform "
            "(client method); per-lamp angles are relative to each lamp."
        ),
        plausible=plausible,
        plausibility_note=plausibility_note,
        nearest_lamp_distance_m=(round(nearest_m, 1) if nearest_m is not None else None),
        elevation_angle_uncertainty_deg=_angle_uncertainty_deg(
            mid_horizontal, up, sigma_horizontal_m, sigma_vertical_m
        ),
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


def _extract_dji_xmp_pose(raw_head: bytes) -> dict[str, float]:
    """RTK-corrected DJI pose from a JPEG's XMP packet (drone-dji:* tags).

    DJI writes the RTK/fused pose into XMP, e.g. ``drone-dji:AbsoluteAltitude="+475.20"``
    (WGS-84 ELLIPSOIDAL height, ~1.5 cm with an RTK fix) plus ``drone-dji:RtkFlag``. The
    EXIF ``GPS GPSAltitude`` is GPS/baro-blended and on non-RTK frames carries 1-15 m of
    vertical error (DJI Enterprise docs) — enough to drag the PAPI elevation angle well
    below the true 2.5-4 deg band. Both attribute (``name="..."``) and element
    (``<name>...</name>``) XMP forms are matched.
    """
    text = raw_head.decode("latin-1", errors="ignore")
    fields = {
        "lat": "GpsLatitude",
        "lon": "GpsLongitude",
        "abs_alt": "AbsoluteAltitude",
        "rel_alt": "RelativeAltitude",
        "rtk_flag": "RtkFlag",
        # RTK per-axis standard deviations (m). DJI writes these next to the pose on
        # an RTK fix; they feed the 1-sigma band on the elevation angle. Additive —
        # existing callers ignore the extra keys. Tag names verified in
        # packages/papi/src/papi/metadata.py (RtkStdLat / RtkStdLon / RtkStdHgt).
        "rtk_std_lat": "RtkStdLat",
        "rtk_std_lon": "RtkStdLon",
        "rtk_std_hgt": "RtkStdHgt",
    }
    pose: dict[str, float] = {}
    for key, name in fields.items():
        match = re.search(rf'drone-dji:{name}(?:="?|>)\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', text)
        if match:
            try:
                pose[key] = float(match.group(1))
            except ValueError:
                pass
    return pose


def extract_gps_metadata(media_path: Path) -> tuple[float, float, float] | None:
    # Prefer the RTK-corrected DJI XMP pose (ellipsoidal AbsoluteAltitude) over EXIF.
    # exifread reads EXIF only; the RTK altitude lives in the XMP APP1 segment near the
    # file start, so a bounded head read is enough and keeps videos cheap. Using EXIF
    # GPSAltitude (1-15 m non-RTK vertical error) is what pushed the computed PAPI angle
    # below 2.5 deg; the RTK ellipsoidal altitude is the fix.
    try:
        with media_path.open("rb") as file:
            head = file.read(262_144)  # 256 KB covers the XMP packet
    except Exception:
        head = b""
    xmp = _extract_dji_xmp_pose(head) if head else {}
    if all(field in xmp for field in ("lat", "lon", "abs_alt")):
        lat, lon, alt = xmp["lat"], xmp["lon"], xmp["abs_alt"]
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0 and -500.0 <= alt <= ALTITUDE_MAX_M:
            return lat, lon, alt

    # Fallback: EXIF GPSAltitude (no RTK XMP present) — less accurate vertically.
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
    # GPSAltitudeRef comes back from exifread as a single-element list (e.g. [1]
    # = below sea level), so read element 0 — comparing the list itself (`[1] == 1`)
    # is always False, so the below-sea-level sign was never applied (audit backend-bugs).
    alt_ref_value = getattr(alt_ref, "values", None) if alt_ref else None
    if isinstance(alt_ref_value, (list, tuple)) and alt_ref_value:
        alt_ref_value = alt_ref_value[0]
    if alt_ref_value == 1:
        altitude = -altitude

    # Range-validate before the values reach the angle math — a corrupted/crafted
    # EXIF (e.g. lat=999) must NOT flow into ENU and fabricate an angle shown as
    # real. Mirrors the manual-metadata validation in validation/analyze.py (audit:
    # extract_gps_metadata had no bounds check while the manual path did).
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None
    if not (-500.0 <= altitude <= ALTITUDE_MAX_M):
        return None

    return latitude, longitude, altitude


def extract_gps_uncertainty(media_path: Path) -> tuple[float, float] | None:
    """RTK ``(sigma_horizontal_m, sigma_vertical_m)`` from a file's DJI XMP, or None.

    Reads the same bounded head as ``extract_gps_metadata`` and pulls the per-axis RTK
    standard deviations DJI writes alongside the pose. Horizontal sigma combines the
    lat/lon components (``hypot``); vertical sigma is the height std. Returns None when
    the file carries no RTK std (manual + telemetry-file fixes never do), so the
    angle's uncertainty band is shown only when it is genuinely measured.
    """
    try:
        with media_path.open("rb") as file:
            head = file.read(262_144)  # 256 KB covers the XMP packet (matches above)
    except Exception:
        return None
    if not head:
        return None

    pose = _extract_dji_xmp_pose(head)
    std_lat = pose.get("rtk_std_lat")
    std_lon = pose.get("rtk_std_lon")
    std_hgt = pose.get("rtk_std_hgt")
    if std_lat is None or std_lon is None or std_hgt is None:
        return None
    # Reject negative/garbage std — a standard deviation is non-negative.
    if std_lat < 0.0 or std_lon < 0.0 or std_hgt < 0.0:
        return None

    return math.hypot(std_lat, std_lon), std_hgt
