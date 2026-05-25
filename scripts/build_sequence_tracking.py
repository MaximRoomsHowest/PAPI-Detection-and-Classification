"""Build per-lamp tracking annotations for the canonical PAPI sequence dataset."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import yaml

from papi.projection import DEFAULT_CONVENTION, ProjectionConvention
from papi.tracking import (
    TRACK_FIELDNAMES,
    TRANSITION_FIELDNAMES,
    assign_frame_tracks,
    detect_transitions,
    read_yolo_detections,
    summarize_tracking,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_projection(path: Path) -> ProjectionConvention:
    if not path.exists():
        return DEFAULT_CONVENTION
    return ProjectionConvention.from_dict(_load_yaml(path)["convention"])


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_tracking(
    dataset_root: Path,
    airport_config_path: Path,
    projection_config_path: Path,
    projection_max_distance_px: float,
) -> dict:
    airport_config = _load_yaml(airport_config_path)
    convention = _load_projection(projection_config_path)
    manifest: dict = {
        "dataset_root": str(dataset_root),
        "projection_max_distance_px": projection_max_distance_px,
        "regimes": {},
        "totals": {
            "track_rows": 0,
            "transitions": 0,
            "transitions_by_type": {},
            "assignment_methods": {},
            "quality_flags": {},
        },
        "errors": [],
        "error_count": 0,
    }

    for regime_root in [dataset_root / "daytime", dataset_root / "nighttime"]:
        if not regime_root.exists():
            manifest["errors"].append(f"missing regime root: {regime_root}")
            continue
        regime_track_rows: list[dict[str, str]] = []
        regime_transition_rows: list[dict[str, str]] = []
        regime_info: dict = {"videos": {}}

        for video_dir in sorted([path for path in regime_root.iterdir() if path.is_dir()]):
            video_track_rows: list[dict[str, str]] = []
            metadata_path = video_dir / "metadata.csv"
            with metadata_path.open(newline="", encoding="utf-8") as fh:
                metadata_rows = list(csv.DictReader(fh))

            for image_row in metadata_rows:
                image_width = int(image_row["image_width"])
                image_height = int(image_row["image_height"])
                label_rel = str(image_row["label"])
                label_path = video_dir / label_rel
                detections = read_yolo_detections(label_path, image_width, image_height)
                video_track_rows.extend(
                    assign_frame_tracks(
                        video_id=video_dir.name,
                        image_row=image_row,
                        label_rel=label_rel,
                        detections=detections,
                        airport_config=airport_config,
                        projection_convention=convention,
                        projection_max_distance_px=projection_max_distance_px,
                    )
                )

            video_transition_rows = detect_transitions(video_track_rows)
            _write_csv(video_dir / "tracks.csv", TRACK_FIELDNAMES, video_track_rows)
            _write_csv(video_dir / "transitions.csv", TRANSITION_FIELDNAMES, video_transition_rows)
            video_summary = summarize_tracking(video_track_rows, video_transition_rows)
            video_summary["frames"] = len(metadata_rows)
            regime_info["videos"][video_dir.name] = video_summary
            regime_track_rows.extend(video_track_rows)
            regime_transition_rows.extend(video_transition_rows)

        regime_info.update(summarize_tracking(regime_track_rows, regime_transition_rows))
        manifest["regimes"][regime_root.name] = regime_info
        _merge_totals(manifest["totals"], regime_info)

    manifest["error_count"] = len(manifest["errors"])
    (dataset_root / "tracking_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _merge_totals(totals: dict, summary: dict) -> None:
    totals["track_rows"] += int(summary.get("track_rows", 0))
    totals["transitions"] += int(summary.get("transitions", 0))
    for key in ("transitions_by_type", "assignment_methods", "quality_flags"):
        for name, count in summary.get(key, {}).items():
            totals[key][name] = totals[key].get(name, 0) + count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=REPO_ROOT / "data" / "datasets" / "papi_lamp_sequences",
    )
    parser.add_argument(
        "--airport-config",
        type=Path,
        default=REPO_ROOT / "configs" / "papi_edny.yaml",
    )
    parser.add_argument(
        "--projection-config",
        type=Path,
        default=REPO_ROOT / "configs" / "projection.yaml",
    )
    parser.add_argument("--projection-max-distance-px", type=float, default=300.0)
    args = parser.parse_args()

    manifest = build_tracking(
        dataset_root=args.dataset_root,
        airport_config_path=args.airport_config,
        projection_config_path=args.projection_config,
        projection_max_distance_px=args.projection_max_distance_px,
    )
    print(json.dumps({"error_count": manifest["error_count"], "totals": manifest["totals"]}, indent=2))
    if manifest["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
