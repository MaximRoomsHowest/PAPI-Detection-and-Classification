#!/usr/bin/env python
"""End-to-end PAPI auto-labelling pipeline.

Run any subset of the 5 stages by name, or `all` to run them in order:

    python workflows/scripts/pipeline.py all                # full pipeline
    python workflows/scripts/pipeline.py all --skip export  # everything except CVAT export
    python workflows/scripts/pipeline.py extract            # just metadata extraction
    python workflows/scripts/pipeline.py calibrate
    python workflows/scripts/pipeline.py autolabel --limit 100
    python workflows/scripts/pipeline.py sample
    python workflows/scripts/pipeline.py export --limit 300

Stages:
    extract    Walk data/raw/<flight>/*.JPG, extract EXIF + DJI XMP -> images_metadata.csv
    calibrate  Brute-force the DJI gimbal Euler convention against LRF bore-sight -> projection.yaml
    autolabel  Project surveyed PAPI lights -> YOLO bboxes (WideCamera only) + lamp_state.csv
    sample     Select the verification sample biased toward boundary cases
    export     Build a CVAT-importable Ultralytics YOLO 1.0 bundle from the verification sample
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from papi.cvat_export import build_ultralytics, zip_bundle  # noqa: E402
from papi.geometry import horizontal_distance_m, resolve_papi_for_frame  # noqa: E402
from papi.global_state import derive_global_state  # noqa: E402
from papi.io import (  # noqa: E402
    LAMP_STATE_CLASS_IDS,
    LAMP_STATE_CLASS_NAMES,
    YOLO_CLASS_ID_PAPI,
    YOLO_CLASS_NAMES,
    write_data_yaml,
    write_yolo_label,
    write_yolo_labels,
)
from papi.lamp_state import compute_lamp_state  # noqa: E402
from papi.metadata import extract_image_metadata  # noqa: E402
from papi.projection import (  # noqa: E402
    DEFAULT_CONVENTION,
    ProjectionConvention,
    project_papi_lights,
    world_to_image,
)
from papi.sampling import select_verification_sample  # noqa: E402
from papi.visual_lamp import detect_visual_lamps  # noqa: E402

# Default artifact paths — every stage takes a CLI override but these are the canonical layout.
DEFAULT_RAW = REPO_ROOT / "data" / "raw"
DEFAULT_METADATA_CSV = REPO_ROOT / "data" / "interim" / "images_metadata.csv"
DEFAULT_LAMP_STATE_CSV = REPO_ROOT / "data" / "interim" / "lamp_state.csv"
DEFAULT_SAMPLE_CSV = REPO_ROOT / "data" / "interim" / "verification_sample.csv"
DEFAULT_LABELS_DIR = REPO_ROOT / "data" / "labels" / "auto"
DEFAULT_DATA_YAML = REPO_ROOT / "data" / "labels" / "data.yaml"
DEFAULT_CVAT_DIR = REPO_ROOT / "data" / "cvat"
DEFAULT_PAPI_CFG = REPO_ROOT / "configs" / "papi_edny.yaml"
DEFAULT_SPLIT_CFG = REPO_ROOT / "configs" / "split.yaml"
DEFAULT_PROJ_CFG = REPO_ROOT / "configs" / "projection.yaml"

STANDOFF_BUCKETS_M = (300, 400, 500, 600, 700, 800, 1000)


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Stage: extract metadata
# ---------------------------------------------------------------------------


def _is_night(folder: str, local_dt: str | None) -> bool:
    if folder and "night" in folder.lower():
        return True
    if not local_dt:
        return False
    try:
        dt = datetime.strptime(local_dt, "%Y:%m:%d %H:%M:%S")
        return dt.hour >= 21 or dt.hour < 6
    except ValueError:
        return False


def _standoff_bucket_m(row: dict, airport_cfg: dict) -> tuple[int | None, str | None]:
    if row["lat"] is None or row["lon"] is None:
        return None, None
    min_dist = float("inf")
    min_runway: str | None = None
    for runway, rcfg in airport_cfg["runways"].items():
        for i in range(1, 5):
            light = rcfg["papi"][f"light_{i}"]
            d = horizontal_distance_m(row["lat"], row["lon"], light["lat"], light["lon"])
            if d < min_dist:
                min_dist = d
                min_runway = str(runway)
    return min(STANDOFF_BUCKETS_M, key=lambda b: abs(b - min_dist)), min_runway


def _split_for(folder: str, split_cfg: dict) -> str:
    if folder in split_cfg.get("test_flights", []):
        return "test"
    if folder in split_cfg.get("val_flights", []):
        return "val"
    return "train"


def stage_extract(args: argparse.Namespace) -> int:
    airport_cfg = _load_yaml(args.papi_config)
    split_cfg = _load_yaml(args.split_config)

    jpgs = sorted(args.raw.glob("*/*.JPG"))
    if args.limit:
        jpgs = jpgs[: args.limit]
    print(f"Found {len(jpgs)} JPGs under {args.raw}", file=sys.stderr)

    rows: list[dict] = []
    for p in tqdm(jpgs, desc="metadata", unit="img"):
        row = extract_image_metadata(p)
        row["is_night"] = _is_night(row["folder"], row.get("local_datetime"))
        bucket, nearer_runway = _standoff_bucket_m(row, airport_cfg)
        row["standoff_bucket_m"] = bucket
        row["nearer_runway"] = nearer_runway
        row["split"] = _split_for(row["folder"], split_cfg)
        rows.append(row)

    df = pd.DataFrame(rows)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.metadata, index=False)
    print(f"Wrote {len(df)} rows -> {args.metadata}", file=sys.stderr)
    print("Camera breakdown:", df["camera"].value_counts(dropna=False).to_dict(), file=sys.stderr)
    print("Split breakdown:", df["split"].value_counts().to_dict(), file=sys.stderr)
    print("Is_night breakdown:", df["is_night"].value_counts().to_dict(), file=sys.stderr)
    print("Nearer runway:", df["nearer_runway"].value_counts(dropna=False).to_dict(), file=sys.stderr)
    print("Standoff bucket:", df["standoff_bucket_m"].value_counts().sort_index().to_dict(), file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Stage: calibrate gimbal
# ---------------------------------------------------------------------------

ENU_SWAPS = {
    "ENU_to_NED": [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]],
    "ENU_identity": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
}
BODY_SWAPS = {
    "body_to_image_fwd": [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
    "body_to_image_alt": [[0.0, 1.0, 0.0], [0.0, 0.0, -1.0], [1.0, 0.0, 0.0]],
}
EULER_ORDERS = ("ZYX", "ZXY", "XYZ", "XZY", "YXZ", "YZX")
SIGN_OPTIONS = (+1, -1)


def _residual(sample: pd.DataFrame, conv: ProjectionConvention, cam_cfg: dict) -> tuple[float, float]:
    fx = fy = float(cam_cfg["calibrated_focal_px"])
    cx = float(cam_cfg["optical_center_x"])
    cy = float(cam_cfg["optical_center_y"])
    w = int(cam_cfg["width"])
    h = int(cam_cfg["height"])

    residuals: list[float] = []
    for row in sample.itertuples(index=False):
        u, v, behind, _ = world_to_image(
            target_lat=row.lrf_target_lat,
            target_lon=row.lrf_target_lon,
            target_alt_m=row.lrf_target_abs_alt_m if pd.notna(row.lrf_target_abs_alt_m) else 465.0,
            camera_lat=row.lat,
            camera_lon=row.lon,
            camera_alt_m=row.alt_ellipsoidal_m,
            gimbal_yaw_deg=row.gimbal_yaw_deg,
            gimbal_pitch_deg=row.gimbal_pitch_deg,
            gimbal_roll_deg=row.gimbal_roll_deg,
            fx_px=fx, fy_px=fy, cx_px=cx, cy_px=cy,
            width=w, height=h,
            convention=conv,
        )
        if behind or u is None:
            residuals.append(1e9)
            continue
        residuals.append(float(np.hypot(u - w / 2.0, v - h / 2.0)))
    return float(np.median(residuals)), float(np.max(residuals))


def stage_calibrate(args: argparse.Namespace) -> int:
    df = pd.read_csv(args.metadata)
    cam_cfg = _load_yaml(args.papi_config)["cameras"]["wide"]

    wide = df[df["camera"] == "WideCamera"]
    lrf = wide[(wide["lrf_status"] == "Normal") & wide["lrf_target_lat"].notna()].copy()
    n_flights = lrf["folder"].nunique()
    per_flight = max(1, args.n_samples // max(1, n_flights))
    sampled = (
        lrf.groupby("folder", group_keys=False)
        .apply(lambda g: g.sample(min(len(g), per_flight), random_state=42))
        .reset_index(drop=True)
    )
    if len(sampled) == 0:
        print("No LRF-Normal WideCamera frames found; cannot calibrate", file=sys.stderr)
        return 2
    print(f"Calibrating against {len(sampled)} LRF-Normal frames across {n_flights} flights", file=sys.stderr)

    candidates = list(itertools.product(
        ENU_SWAPS.items(), EULER_ORDERS,
        SIGN_OPTIONS, SIGN_OPTIONS, SIGN_OPTIONS,
        BODY_SWAPS.items(), (False, True),
    ))
    print(f"Searching {len(candidates)} conventions...", file=sys.stderr)

    best: dict | None = None
    for (enu_name, enu_mat), order, sy, sp, sr, (body_name, body_mat), invert in tqdm(candidates, desc="search"):
        conv = ProjectionConvention(
            enu_to_intermediate=np.array(enu_mat),
            euler_order=order,
            yaw_sign=sy, pitch_sign=sp, roll_sign=sr,
            body_to_image=np.array(body_mat),
            invert_rotation=invert,
        )
        median_px, max_px = _residual(sampled, conv, cam_cfg)
        if best is None or median_px < best["median_px"]:
            best = {
                "median_px": median_px, "max_px": max_px,
                "enu_swap": enu_name, "euler_order": order,
                "yaw_sign": sy, "pitch_sign": sp, "roll_sign": sr,
                "body_swap": body_name, "invert_rotation": invert,
                "conv": conv,
            }

    assert best is not None
    print(
        f"\nBest: enu_swap={best['enu_swap']}, order={best['euler_order']}, "
        f"signs=(y={best['yaw_sign']}, p={best['pitch_sign']}, r={best['roll_sign']}), "
        f"body_swap={best['body_swap']}, invert={best['invert_rotation']}, "
        f"median_residual={best['median_px']:.1f}px, max_residual={best['max_px']:.1f}px",
        file=sys.stderr,
    )
    if best["median_px"] > args.median_gate_px:
        print(f"WARNING: median residual exceeds gate {args.median_gate_px}px", file=sys.stderr)
    if best["max_px"] > args.max_gate_px:
        print(f"WARNING: max residual exceeds gate {args.max_gate_px}px", file=sys.stderr)

    args.projection_config.parent.mkdir(parents=True, exist_ok=True)
    with args.projection_config.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            {
                "note": "Written by workflows/scripts/pipeline.py calibrate -- re-run if camera or gimbal config changes",
                "calibrated_against_n_frames": int(len(sampled)),
                "median_residual_px": best["median_px"],
                "max_residual_px": best["max_px"],
                "enu_swap_name": best["enu_swap"],
                "body_swap_name": best["body_swap"],
                "convention": best["conv"].to_dict(),
            },
            fh, sort_keys=False, default_flow_style=False,
        )
    print(f"Wrote {args.projection_config}", file=sys.stderr)
    return 0 if best["median_px"] <= args.median_gate_px else 1


# ---------------------------------------------------------------------------
# Stage: autolabel
# ---------------------------------------------------------------------------


def _load_convention(path: Path) -> ProjectionConvention:
    if not path.exists():
        print(f"WARN: {path} not found -- using DEFAULT_CONVENTION. Run `calibrate` first.", file=sys.stderr)
        return DEFAULT_CONVENTION
    return ProjectionConvention.from_dict(_load_yaml(path)["convention"])


def _build_bbox(
    projected: dict[int, tuple[float | None, float | None, bool, bool]],
    width: int, height: int,
) -> tuple[float, float, float, float] | None:
    pts: list[tuple[float, float]] = []
    for _, (u, v, behind, _) in projected.items():
        if behind or u is None:
            continue
        pts.append((
            max(0.0, min(float(width - 1), u)),
            max(0.0, min(float(height - 1), v)),
        ))
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    pad = max(20.0, 0.4 * max(x2 - x1, y2 - y1))
    x1 = max(0.0, x1 - pad)
    y1 = max(0.0, y1 - pad)
    x2 = min(float(width - 1), x2 + pad)
    y2 = min(float(height - 1), y2 + pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _build_lamp_bbox(
    projected: dict[int, tuple[float | None, float | None, bool, bool]],
    light_no: int,
    width: int,
    height: int,
) -> tuple[float, float, float, float] | None:
    u, v, behind, in_frame = projected[light_no]
    if behind or not in_frame or u is None or v is None:
        return None

    visible: list[tuple[float, float]] = []
    for other_u, other_v, other_behind, other_in_frame in projected.values():
        if other_behind or not other_in_frame or other_u is None or other_v is None:
            continue
        visible.append((float(other_u), float(other_v)))

    distances = [
        float(np.hypot(float(u) - other_u, float(v) - other_v))
        for other_u, other_v in visible
        if other_u != float(u) or other_v != float(v)
    ]
    nearest_spacing = min(distances) if distances else 40.0
    half_size = max(10.0, min(80.0, 0.35 * nearest_spacing))

    x1 = max(0.0, float(u) - half_size)
    y1 = max(0.0, float(v) - half_size)
    x2 = min(float(width - 1), float(u) + half_size)
    y2 = min(float(height - 1), float(v) + half_size)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _coverage_class(projected: dict[int, tuple]) -> str:
    in_frame = sum(1 for _, _, behind, inf in projected.values() if inf and not behind)
    return f"{in_frame}_in_frame"


def stage_autolabel(args: argparse.Namespace) -> int:
    df = pd.read_csv(args.metadata)
    cfg = _load_yaml(args.papi_config)
    cams = cfg["cameras"]
    conv = _load_convention(args.projection_config)

    if args.limit:
        df = df.head(args.limit)
    print(f"Auto-labelling {len(df)} frames", file=sys.stderr)

    lamp_rows: list[dict] = []
    coverage = Counter()
    runway_counts = Counter()
    bbox_written = 0

    for row in tqdm(df.itertuples(index=False), total=len(df), desc="autolabel", unit="img"):
        row_d = row._asdict()
        camera = row_d.get("camera")
        cam_cfg = cams.get("wide" if camera == "WideCamera" else "zoom" if camera == "ZoomCamera" else None)

        try:
            runway, papi_cfg = resolve_papi_for_frame(row_d, cfg)
        except (KeyError, TypeError, ValueError):
            runway, papi_cfg = "unknown", None  # type: ignore[assignment]
        runway_counts[runway] += 1

        try:
            assert papi_cfg is not None
            lamps, min_margin = compute_lamp_state(row_d, papi_cfg)
            global_state = derive_global_state(lamps)
        except (AssertionError, TypeError, ValueError):
            lamps = ("unknown",) * 4
            min_margin = None  # type: ignore[assignment]
            global_state = None  # type: ignore[assignment]

        bbox_ok = False
        if camera == "WideCamera" and cam_cfg and cam_cfg.get("calibrated_focal_px") is not None and papi_cfg is not None:
            try:
                proj = project_papi_lights(row_d, papi_cfg, cam_cfg, conv)
            except (TypeError, ValueError):
                proj = {}
            if proj:
                coverage[_coverage_class(proj)] += 1
                bbox = _build_bbox(proj, cam_cfg["width"], cam_cfg["height"])
                if bbox is not None:
                    label_path = args.labels_dir / row_d["folder"] / (Path(row_d["file"]).stem + ".txt")
                    write_yolo_label(
                        label_path, class_id=YOLO_CLASS_ID_PAPI,
                        bbox_xyxy_px=bbox,
                        image_width=int(cam_cfg["width"]),
                        image_height=int(cam_cfg["height"]),
                    )
                    bbox_ok = True
                    bbox_written += 1

        lamp_rows.append({
            "folder": row_d["folder"], "file": row_d["file"],
            "light_1_state": lamps[0], "light_2_state": lamps[1],
            "light_3_state": lamps[2], "light_4_state": lamps[3],
            "global_state": global_state, "min_angle_margin_deg": min_margin,
            "camera": camera, "target_runway": runway, "bbox_written": bbox_ok,
        })

    lamp_df = pd.DataFrame(lamp_rows)
    args.lamp_state.parent.mkdir(parents=True, exist_ok=True)
    lamp_df.to_csv(args.lamp_state, index=False)
    write_data_yaml(args.data_yaml)
    print(f"Wrote {args.lamp_state} ({len(lamp_df)} rows) + {args.data_yaml}", file=sys.stderr)
    print(f"BBox written: {bbox_written}/{len(df)} (WideCamera only)", file=sys.stderr)
    print(f"Target runway: {dict(runway_counts)}", file=sys.stderr)
    print(f"Lamp coverage: {dict(coverage)}", file=sys.stderr)
    print(f"Global state: {lamp_df['global_state'].value_counts(dropna=False).to_dict()}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Stage: sample verification
# ---------------------------------------------------------------------------


def stage_sample(args: argparse.Namespace) -> int:
    meta = pd.read_csv(args.metadata)
    lamp = pd.read_csv(args.lamp_state)
    sample = select_verification_sample(
        meta, lamp, every_n=args.every_n, transition_margin_deg=args.transition_margin_deg,
    )
    args.sample.parent.mkdir(parents=True, exist_ok=True)
    sample.to_csv(args.sample, index=False)
    print(f"Sampled {len(sample)} / {len(meta)} frames ({100*len(sample)/max(1,len(meta)):.1f}%)", file=sys.stderr)
    counts: Counter[str] = Counter()
    for r in sample["reason"]:
        for tok in str(r).split(","):
            if tok:
                counts[tok] += 1
    print("Per-reason counts:", file=sys.stderr)
    for reason, n in counts.most_common():
        print(f"  {reason}: {n}", file=sys.stderr)
    print(f"Wrote {args.sample}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Stage: export CVAT
# ---------------------------------------------------------------------------


def _write_lamp_state_labels(
    sample: pd.DataFrame,
    args: argparse.Namespace,
) -> Path:
    labels_dir = args.cvat_dir.parent / f"{args.cvat_dir.name}_lamp_state_labels"
    if labels_dir.exists():
        import shutil

        shutil.rmtree(labels_dir)

    rows_written = 0
    objects_written = 0
    state_counts: Counter[str] = Counter()

    for row in sample.itertuples(index=False):
        row_d = row._asdict()
        folder = row_d["folder"]
        fname = row_d["file"]
        label_path = labels_dir / folder / (Path(fname).stem + ".txt")
        labels: list[tuple[int, tuple[float, float, float, float]]] = []

        for detection in detect_visual_lamps(args.raw / folder / fname):
            class_id = LAMP_STATE_CLASS_IDS.get(detection.state)
            if class_id is None:
                continue
            labels.append((class_id, detection.bbox_xyxy_px))
            state_counts[detection.state] += 1

        write_yolo_labels(
            label_path,
            labels,
            int(row_d["image_width"]),
            int(row_d["image_height"]),
        )
        rows_written += 1
        objects_written += len(labels)

    print(
        f"Wrote per-lamp state labels: {objects_written} objects across "
        f"{rows_written} frames -> {labels_dir}",
        file=sys.stderr,
    )
    print(f"Per-lamp state objects: {dict(state_counts)}", file=sys.stderr)
    return labels_dir


def stage_export(args: argparse.Namespace) -> int:
    sample = pd.read_csv(args.sample)
    if args.limit:
        sample = sample.head(args.limit)
    args.cvat_dir.mkdir(parents=True, exist_ok=True)
    rows = sample.to_dict(orient="records")
    labels_dir = args.labels_dir
    class_names = YOLO_CLASS_NAMES
    if args.annotation_granularity == "lamp-state":
        labels_dir = _write_lamp_state_labels(sample, args)
        class_names = LAMP_STATE_CLASS_NAMES
    print(f"Building Ultralytics YOLO 1.0 bundle for {len(rows)} frames -> {args.cvat_dir}/", file=sys.stderr)
    data_yaml = build_ultralytics(
        rows,
        args.raw,
        labels_dir,
        args.cvat_dir,
        include_images=not args.annotations_only,
        image_name_mode=args.image_name_mode,
        class_names=class_names,
    )
    print(f"Wrote {data_yaml}", file=sys.stderr)
    zip_out = args.zip_out or (args.cvat_dir / f"papi_verification_sample_{datetime.now().strftime('%Y%m%d')}.zip")
    zp = zip_bundle(args.cvat_dir, zip_out)
    print(f"Wrote {zp}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------

STAGES = {
    "extract": stage_extract,
    "calibrate": stage_calibrate,
    "autolabel": stage_autolabel,
    "sample": stage_sample,
    "export": stage_export,
}
DEFAULT_ORDER = ["extract", "calibrate", "autolabel", "sample", "export"]


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--raw", default=DEFAULT_RAW, type=Path)
    p.add_argument("--metadata", default=DEFAULT_METADATA_CSV, type=Path)
    p.add_argument("--lamp-state", default=DEFAULT_LAMP_STATE_CSV, type=Path)
    p.add_argument("--sample", default=DEFAULT_SAMPLE_CSV, type=Path)
    p.add_argument("--labels-dir", default=DEFAULT_LABELS_DIR, type=Path)
    p.add_argument("--data-yaml", default=DEFAULT_DATA_YAML, type=Path)
    p.add_argument("--cvat-dir", default=DEFAULT_CVAT_DIR, type=Path)
    p.add_argument("--papi-config", default=DEFAULT_PAPI_CFG, type=Path)
    p.add_argument("--split-config", default=DEFAULT_SPLIT_CFG, type=Path)
    p.add_argument("--projection-config", default=DEFAULT_PROJ_CFG, type=Path)
    p.add_argument("--limit", type=int, default=0, help="Process at most N rows (0 = all)")
    p.add_argument("--n-samples", type=int, default=50, help="LRF calibration sample size")
    p.add_argument("--median-gate-px", type=float, default=100.0)
    p.add_argument("--max-gate-px", type=float, default=300.0)
    p.add_argument("--every-n", type=int, default=8, help="Stratified sampling stride")
    p.add_argument("--transition-margin-deg", type=float, default=0.3)
    p.add_argument("--zip-out", default=None, type=Path)
    p.add_argument(
        "--annotations-only",
        action="store_true",
        help="Export labels/config only for uploading annotations to an existing CVAT task/job",
    )
    p.add_argument(
        "--image-name-mode",
        choices=("flat", "original"),
        default="flat",
        help="Use folder-prefixed names for dataset imports, or original image names to match an existing CVAT task",
    )
    p.add_argument(
        "--annotation-granularity",
        choices=("installation", "lamp-state"),
        default="installation",
        help="Export one installation box per image or one state-labelled box per visible PAPI lamp",
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in STAGES:
        p = sub.add_parser(name, help=f"run only the `{name}` stage")
        _add_common_args(p)

    p_all = sub.add_parser("all", help="run all stages in order")
    _add_common_args(p_all)
    p_all.add_argument("--skip", default="", help="Comma-separated stages to skip")
    p_all.add_argument("--only", default="", help="Comma-separated stages to run (overrides default order)")

    args = parser.parse_args()

    if args.cmd == "all":
        only = [s.strip() for s in args.only.split(",") if s.strip()]
        skip = {s.strip() for s in args.skip.split(",") if s.strip()}
        order = only or DEFAULT_ORDER
        rc = 0
        for stage in order:
            if stage in skip:
                print(f"\n>>> skipping `{stage}` <<<", file=sys.stderr)
                continue
            if stage not in STAGES:
                print(f"Unknown stage: {stage}", file=sys.stderr)
                return 2
            print(f"\n>>> running `{stage}` <<<", file=sys.stderr)
            rc = STAGES[stage](args) or rc
        return rc

    return STAGES[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
