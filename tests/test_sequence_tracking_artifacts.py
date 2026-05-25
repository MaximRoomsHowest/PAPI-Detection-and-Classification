"""Validation tests for generated sequence tracking artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SEQUENCE_ROOT = REPO_ROOT / "data" / "datasets" / "papi_lamp_sequences"


pytestmark = pytest.mark.skipif(
    not SEQUENCE_ROOT.exists(),
    reason="generated sequence dataset artifacts are not committed",
)


def test_tracking_manifest_matches_sequence_dataset_counts():
    manifest_path = SEQUENCE_ROOT / "tracking_manifest.json"
    assert manifest_path.exists(), "run scripts/build_sequence_tracking.py"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validation = json.loads((SEQUENCE_ROOT / "validation_summary.json").read_text(encoding="utf-8"))
    expected_objects = sum(
        regime_summary["objects"]
        for regime_summary in validation["summary"].values()
    )

    assert manifest["error_count"] == 0
    assert manifest["totals"]["track_rows"] == expected_objects
    assert set(manifest["totals"]["transitions_by_type"]) <= {"white_to_red", "red_to_white"}


def test_tracking_rows_have_unique_track_ids_per_frame():
    for tracks_path in SEQUENCE_ROOT.glob("*/*/tracks.csv"):
        with tracks_path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        by_frame: dict[str, list[str]] = {}
        for row in rows:
            by_frame.setdefault(row["frame_index"], []).append(row["track_id"])

        for frame_index, track_ids in by_frame.items():
            assert len(track_ids) == len(set(track_ids)), f"{tracks_path}:{frame_index}"


def test_yolo26n_combined_split_entries_resolve_to_images_and_labels():
    combined = SEQUENCE_ROOT / "yolo26n_combined"
    assert combined.exists(), "run scripts/prepare_yolo_sequence_dataset.py"

    for split in ("train", "val", "test"):
        entries = [
            line.strip()
            for line in (combined / f"{split}.txt").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert entries, f"{split}.txt should not be empty"
        for entry in entries:
            image = (combined / entry).resolve()
            assert image.exists(), entry
            label = image.parent.parent / "labels" / f"{image.stem}.txt"
            assert label.exists(), str(label)
