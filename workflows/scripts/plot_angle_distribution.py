"""Plot the drone->PAPI elevation-angle distribution per runway.

Aggregates every ``metadata.csv`` under a ``papi_lamp_sequences`` dataset, computes
the WGS-84 LLA->ECEF->ENU elevation angle from each frame's RTK drone position
(``alt_ellipsoidal_m``) to the *nearer* PAPI midpoint (461.37 m datum), splits by the
dataset's own ``nearer_runway`` label, and renders an overlaid histogram comparing
Runway 24 (day) vs Runway 06 (night) -- the same angle the backend serves, which is
validated to ~0.02 deg against the client's tool.

Usage:
    python workflows/scripts/plot_angle_distribution.py [DATASET_DIR] [OUT_PNG]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.services.angle import _elevation_from_enu, _geodetic_to_enu  # noqa: E402
from app.services.runways import get_runway  # noqa: E402

DEFAULT_DATASET = Path(
    "C:/Users/rodri/source/howest/25-26/industryproject/PAPI-artifacts/"
    "2026-05-26-cleanup/data/datasets/papi_lamp_sequences"
)


def _midpoint(runway_id: str) -> tuple[float, float, float]:
    lights = get_runway(runway_id)["lights"]
    n = len(lights)
    return (
        sum(light["latitude"] for light in lights) / n,
        sum(light["longitude"] for light in lights) / n,
        sum(light["altitude_m"] for light in lights) / n,
    )


def main(dataset_dir: Path, out_png: Path) -> None:
    mids = {"24": _midpoint("papi_24"), "06": _midpoint("papi_06")}
    angles: dict[str, list[float]] = {"24": [], "06": []}

    csvs = sorted(dataset_dir.rglob("metadata.csv"))
    if not csvs:
        print(f"No metadata.csv found under {dataset_dir}")
        return

    needed = {"lat", "lon", "alt_ellipsoidal_m", "nearer_runway"}
    for csv in csvs:
        df = pd.read_csv(csv)
        if not needed.issubset(df.columns):
            continue
        for lat, lon, alt, rwy in zip(
            df["lat"], df["lon"], df["alt_ellipsoidal_m"], df["nearer_runway"]
        ):
            s = str(rwy).strip()
            key = "24" if s in ("24", "papi_24") else ("06" if s in ("6", "06", "papi_06") else None)
            if key is None or not np.isfinite([lat, lon, alt]).all():
                continue
            mlat, mlon, malt = mids[key]
            _, angle = _elevation_from_enu(
                *_geodetic_to_enu(float(lat), float(lon), float(alt), mlat, mlon, malt)
            )
            angles[key].append(angle)

    for key in ("24", "06"):
        values = angles[key]
        if values:
            print(
                f"Runway {key} angle_deg min/max: {min(values)} {max(values)}  "
                f"(n={len(values)})"
            )

    plt.figure(figsize=(10, 6))
    bins = np.arange(0.5, 4.8, 0.05)
    if angles["24"]:
        plt.hist(angles["24"], bins=bins, alpha=0.6, label="Runway 24", color="tab:blue")
    if angles["06"]:
        plt.hist(angles["06"], bins=bins, alpha=0.6, label="Runway 06", color="tab:orange")
    plt.title("Angle Distribution Comparison (degrees)")
    plt.xlabel("Angle (degrees)")
    plt.ylabel("Count")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=120)
    print(f"saved {out_png}")


if __name__ == "__main__":
    dataset = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATASET
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else (ROOT / "angle_distribution.png")
    main(dataset, out)
