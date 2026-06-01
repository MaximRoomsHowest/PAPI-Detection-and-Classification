"""Diagnose the PAPI elevation-angle altitude source on the real dataset.

For every drone image it recomputes the WGS-84 LLA->ECEF->ENU elevation angle (to the
nearer PAPI midpoint) using BOTH:
  * EXIF ``GPS GPSAltitude``  -- what the data_analysis notebook + the old backend used
    (GPS/baro blend, 1-15 m non-RTK vertical error per DJI Enterprise docs), and
  * the RTK-corrected DJI XMP ``drone-dji:AbsoluteAltitude`` (ellipsoidal, ~1.5 cm).

...and reports how many angles land in the valid 2.5-4 deg PAPI band with each source,
plus the mean altitude delta. This is the empirical check that the RTK altitude is the
fix for the "angles below 2.5 deg" problem.

Run from the repo root:
    python workflows/scripts/diagnose_angle_altitude.py <dataset_dir>
e.g.    python workflows/scripts/diagnose_angle_altitude.py ./dataset
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.services.angle import (  # noqa: E402
    _extract_dji_xmp_pose,
    compute_elevation_angles,
    haversine,
)
from app.services.runways import get_runway  # noqa: E402

BAND = (2.5, 4.0)


def exif_pose(path: Path):
    """(lat, lon, alt) from EXIF GPS tags, or None."""
    try:
        import exifread
    except ImportError:
        return None
    try:
        with path.open("rb") as handle:
            tags = exifread.process_file(handle, details=False)

        def dms(value):
            d, m, s = value.values
            return float(d.num / d.den) + float(m.num / m.den) / 60 + float(s.num / s.den) / 3600

        lat = dms(tags["GPS GPSLatitude"])
        lon = dms(tags["GPS GPSLongitude"])
        if str(tags.get("GPS GPSLatitudeRef")) not in ("N", "None"):
            lat = -lat
        if str(tags.get("GPS GPSLongitudeRef")) not in ("E", "None"):
            lon = -lon
        alt_v = tags["GPS GPSAltitude"].values[0]
        alt = float(alt_v.num / alt_v.den)
        return lat, lon, alt
    except Exception:
        return None


def nearer_runway(lat: float, lon: float) -> str:
    best, best_d = "papi_24", 1e18
    for rid in ("papi_06", "papi_24"):
        lights = get_runway(rid)["lights"]
        mid_lat = sum(light["latitude"] for light in lights) / len(lights)
        mid_lon = sum(light["longitude"] for light in lights) / len(lights)
        d = haversine(lat, lon, mid_lat, mid_lon)
        if d < best_d:
            best_d, best = d, rid
    return best


def summarize(label: str, angles: list[float]) -> None:
    if not angles:
        print(f"  {label:40s}: no angles")
        return
    in_band = sum(1 for a in angles if BAND[0] <= a <= BAND[1])
    below = sum(1 for a in angles if a < BAND[0])
    print(
        f"  {label:40s}: n={len(angles):5d}  min={min(angles):5.2f}  max={max(angles):5.2f}  "
        f"mean={sum(angles) / len(angles):5.2f}  in[2.5,4]={100 * in_band / len(angles):3.0f}%  "
        f"below2.5={100 * below / len(angles):3.0f}%"
    )


def main(dataset_dir: str) -> None:
    root = Path(dataset_dir)
    images = sorted({*root.rglob("*.JPG"), *root.rglob("*.jpg")})
    if not images:
        print(f"No .jpg images under {root}")
        return

    exif_angles: list[float] = []
    rtk_angles: list[float] = []
    deltas: list[float] = []
    rtk_flags: list[float] = []

    for path in images:
        ep = exif_pose(path)
        try:
            with path.open("rb") as handle:
                head = handle.read(262_144)
        except OSError:
            head = b""
        xp = _extract_dji_xmp_pose(head)

        lat, lon = (xp.get("lat"), xp.get("lon"))
        if lat is None or lon is None:
            if ep is None:
                continue
            lat, lon = ep[0], ep[1]
        rid = nearer_runway(lat, lon)

        if ep is not None:
            exif_angles.append(compute_elevation_angles(ep[0], ep[1], ep[2], rid).elevation_angle_deg)
        if "abs_alt" in xp:
            rtk_angles.append(compute_elevation_angles(lat, lon, xp["abs_alt"], rid).elevation_angle_deg)
            if ep is not None:
                deltas.append(xp["abs_alt"] - ep[2])
        if "rtk_flag" in xp:
            rtk_flags.append(xp["rtk_flag"])

    print(f"\nImages scanned: {len(images)}\n")
    summarize("EXIF GPSAltitude (notebook / old)", exif_angles)
    summarize("RTK XMP AbsoluteAltitude (fix)", rtk_angles)
    if deltas:
        print(f"\n  mean(XMP_AbsoluteAltitude - EXIF_GPSAltitude) = {sum(deltas) / len(deltas):+.2f} m "
              f"over {len(deltas)} frames")
    if rtk_flags:
        print(f"  RtkFlag distribution: {dict(Counter(rtk_flags))}  "
              f"(50 = RTK FIX / accurate; other = single/float -> needs PPK via .MRK)")
    if not rtk_angles:
        print("\n  No DJI XMP AbsoluteAltitude found in these images. If the angles are still "
              "below 2.5 deg, the RTK altitude must be recovered from the .MRK PPK side-files.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python workflows/scripts/diagnose_angle_altitude.py <dataset_dir>")
        sys.exit(1)
    main(sys.argv[1])
