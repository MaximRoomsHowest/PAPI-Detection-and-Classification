#!/usr/bin/env python3
"""Build the **real** Live-Demo test media from the project dataset.

Source: ``data/datasets/transition-classification-data/`` (git-ignored, ~5 MB/frame full-res,
5280x3956). This curates a DIVERSE set (distance / day-night / runway) and **downscales each full
frame to 1280 px long-edge** — the WHOLE field of view, NOT a crop. That matters: the detector is
trained on full frames and resizes internally to 1280, so the PAPI lamps must stay at their
full-frame scale. A PAPI-centred *crop* blows the lamps up out of the training distribution and the
model detects **nothing** (measured: 4/4 on the full/downscaled frame, 0/4 on a 1600x1200 crop).
Telemetry (CSV / SRT / JSON) is derived from each clip's ``metadata.csv`` — real drone
``lat / lon / alt_ellipsoidal_m`` — so the angle readout is real. Ground-truth red->white
transitions live in each clip's ``transitions.csv``.

Run from the repo root (uses the repo .venv: cv2 / PIL / numpy):
    .venv/Scripts/python.exe docs/user-testing/build_media.py             # commit the crops + telemetry
    .venv/Scripts/python.exe docs/user-testing/build_media.py --full-res  # full uncropped frames -> media/_fullres (git-ignored)

Idempotent: clears and rebuilds the curated folders each run.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATASET = REPO / "data" / "datasets" / "transition-classification-data"
LONG_EDGE = 1280  # downscale the FULL frame to this long edge (no crop — preserves detection)

CLIPS = {
    "day_300m": "daytime/DJI_202604291738_041_300mday2up",
    "day_700m": "daytime/DJI_202604281946_011_700",
    "day_1000m": "daytime/DJI_202604281946_014_1000",
    "night_300m": "nighttime/DJI_202604290007_019_300mRwy06night",
    "night_500m": "nighttime/DJI_202604290007_023_500mrwy06night",
}


def _load_meta(clip_dir: Path) -> list[dict]:
    rows = list(csv.DictReader(open(clip_dir / "metadata.csv", newline="", encoding="utf-8")))
    rows.sort(key=lambda r: int(r["sequence_index"]))
    return rows


def _runway(rows: list[dict]) -> str:
    return "papi_06" if str(rows[0].get("nearer_runway", "")).strip() in ("6", "06") else "papi_24"


def _pick(rows: list[dict], n: int, lo: float, hi: float) -> list[dict]:
    a, b = int(len(rows) * lo), int(len(rows) * hi) - 1
    if n == 1:
        return [rows[(a + b) // 2]]
    return [rows[a + round(i * (b - a) / (n - 1))] for i in range(n)]


def _emit_frame(clip_dir: Path, row: dict, dst: Path, full_res: bool) -> None:
    """Downscale the FULL frame (whole field of view) to LONG_EDGE — never crop, so the lamps
    keep their full-frame scale and the detector still finds them."""
    from PIL import Image

    img = Image.open(clip_dir / row["image"]).convert("RGB")
    if not full_res:
        w, h = img.size
        s = LONG_EDGE / max(w, h)
        if s < 1:
            img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=88)


def _emit_folder(rows: list[dict], clip_dir: Path, out_dir: Path, full_res: bool) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(rows, 1):
        _emit_frame(clip_dir, r, out_dir / f"frame_{i:03d}.jpg", full_res)


def _ts(x: float) -> str:
    return f"00:00:{int(x):02d},{int((x % 1) * 1000):03d}"


def _emit_telemetry(rows: list[dict], stem: str, runway: str, note: str, single: bool = False) -> None:
    tel = HERE / "telemetry"
    pts = [(i, float(r["lat"]), float(r["lon"]), float(r["alt_ellipsoidal_m"])) for i, r in enumerate(rows)]
    for sub in ("csv", "srt", "json"):
        (tel / sub).mkdir(parents=True, exist_ok=True)

    if single:  # one fix -> a bare {lat,lon,alt} JSON for the single-image upload test
        _, lat, lon, alt = pts[len(pts) // 2]
        (tel / "json" / f"{stem}.json").write_text(
            '{\n  "runway": "%s",\n  "note": "%s",\n  "latitude": %.8f,\n  "longitude": %.8f,\n'
            '  "altitude_m": %.3f\n}\n' % (runway, note, lat, lon, alt),
            encoding="utf-8",
        )
        return

    with open(tel / "csv" / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        fh.write("frame_index,latitude,longitude,altitude_m\n")
        for idx, lat, lon, alt in pts:
            fh.write(f"{idx},{lat:.8f},{lon:.8f},{alt:.3f}\n")

    samples = ",\n".join(
        f'    {{ "frame_index": {idx}, "latitude": {lat:.8f}, "longitude": {lon:.8f}, "altitude_m": {alt:.3f} }}'
        for idx, lat, lon, alt in pts
    )
    (tel / "json" / f"{stem}.json").write_text(
        '{\n  "runway": "%s",\n  "note": "%s",\n  "samples": [\n%s\n  ]\n}\n' % (runway, note, samples),
        encoding="utf-8",
    )

    lines = []
    for idx, lat, lon, alt in pts:
        lines += [
            str(idx + 1),
            f"{_ts(idx * 0.2)} --> {_ts((idx + 1) * 0.2)}",
            f'<font size="28">SrtCnt : {idx + 1}, DiffTime : 200ms',
            "2026-04-29 17:38:00.000",
            f"[latitude: {lat:.8f}] [longitude: {lon:.8f}] [rel_alt: 0.000 abs_alt: {alt:.3f}]</font>",
            "",
        ]
    (tel / "srt" / f"{stem}.srt").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full-res", action="store_true", help="uncropped full frames -> media/_fullres (git-ignored)")
    args = ap.parse_args()

    if not DATASET.exists():
        print(f"Dataset not found at {DATASET} — it is git-ignored; this script needs the local")
        print("transition-classification-data to curate real frames. Nothing built.")
        return 1

    clips = {k: _load_meta(DATASET / v) for k, v in CLIPS.items() if (DATASET / v).exists()}
    if not clips:
        print("No curated clips present locally; skipping.")
        return 1

    media = HERE / ("media/_fullres" if args.full_res else "media")
    print(f"Building {'FULL-RES' if args.full_res else 'downscaled-full 1280px'} real media ...")
    summary = []

    # Single images: spread of distance / lighting (early=more red, late=more white after the sweep).
    singles = media / "single-image"
    if singles.exists():
        shutil.rmtree(singles)
    singles.mkdir(parents=True, exist_ok=True)
    single_spec = [
        ("day_300m", 0.20, "papi24_day_300m_early"),
        ("day_300m", 0.95, "papi24_day_300m_late"),
        ("day_700m", 0.85, "papi24_day_700m"),
        ("day_1000m", 0.50, "papi24_day_1000m_far"),
        ("night_300m", 0.50, "papi06_night_300m"),
        ("night_500m", 0.80, "papi06_night_500m"),
    ]
    for key, frac, name in single_spec:
        if key not in clips:
            continue
        r = _pick(clips[key], 1, frac, min(frac + 0.001, 1.0))[0]
        _emit_frame(DATASET / CLIPS[key], r, singles / f"{name}.jpg", args.full_res)
        summary.append(f"  single  {name:24s} {_runway(clips[key])} seq {r['sequence_index']}")
    # One real single-fix JSON matching the early 300m single, for the single-image upload test.
    if "day_300m" in clips and not args.full_res:
        r = _pick(clips["day_300m"], 1, 0.20, 0.201)
        _emit_telemetry(r, "point_papi24", "papi_24", "Real single drone fix for a papi_24 single image.", single=True)

    # Sweeps — real descents; serve both angle-sweep AND folder-as-video (toggle mode). Paired telemetry.
    sweep_spec = [
        ("day_300m", 10, 0.30, 0.97, "sweep_papi24_300m_day", "papi24_300m_day"),
        ("night_300m", 8, 0.20, 0.97, "sweep_papi06_300m_night", "papi06_300m_night"),
    ]
    for key, n, lo, hi, folder, stem in sweep_spec:
        if key not in clips:
            continue
        picked = _pick(clips[key], n, lo, hi)
        rwy = _runway(clips[key])
        _emit_folder(picked, DATASET / CLIPS[key], media / "image-batch" / folder, args.full_res)
        if not args.full_res:
            _emit_telemetry(picked, stem, rwy, f"Real per-frame drone fixes for {folder} (EDNY {rwy}).")
        summary.append(f"  sweep   {folder:24s} {rwy} {n} frames + telemetry/{stem}.(csv|srt|json)")

    print("\n".join(summary))
    print(f"Done — {len(summary)} sets under {media.relative_to(REPO)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
