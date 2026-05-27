from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from papi.cvat_export import build_ultralytics


def test_build_ultralytics_resets_stale_bundle_and_keeps_empty_labels(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    labels_dir = tmp_path / "labels"
    out_dir = tmp_path / "cvat"

    (raw_dir / "flight_a").mkdir(parents=True)
    (raw_dir / "flight_a" / "img_001.JPG").write_bytes(b"fake image")

    (labels_dir / "flight_a").mkdir(parents=True)
    (labels_dir / "flight_a" / "img_001.txt").write_text(
        "0 0.500000 0.500000 0.250000 0.250000\n",
        encoding="utf-8",
    )

    (raw_dir / "flight_b").mkdir(parents=True)
    (raw_dir / "flight_b" / "img_002.JPG").write_bytes(b"fake zoom image")

    stale_image = out_dir / "images" / "train" / "stale.JPG"
    stale_label = out_dir / "labels" / "val" / "stale.txt"
    stale_image.parent.mkdir(parents=True)
    stale_label.parent.mkdir(parents=True)
    stale_image.write_bytes(b"stale")
    stale_label.write_text("0 0.1 0.1 0.1 0.1\n", encoding="utf-8")
    (out_dir / "train.txt").write_text("./images/train/stale.JPG\n", encoding="utf-8")
    (out_dir / "data.yaml").write_text("stale: true\n", encoding="utf-8")

    rows = [
        {"folder": "flight_a", "file": "img_001.JPG", "split": "train"},
        {"folder": "flight_b", "file": "img_002.JPG", "split": "test"},
    ]

    data_yaml = build_ultralytics(rows, raw_dir, labels_dir, out_dir)

    assert not stale_image.exists()
    assert not stale_label.exists()
    assert (out_dir / "images" / "train" / "flight_a__img_001.JPG").exists()
    assert (out_dir / "images" / "val" / "flight_b__img_002.JPG").exists()
    assert (out_dir / "labels" / "train" / "flight_a__img_001.txt").read_text(
        encoding="utf-8"
    ) == "0 0.500000 0.500000 0.250000 0.250000\n"
    assert (out_dir / "labels" / "val" / "flight_b__img_002.txt").read_text(
        encoding="utf-8"
    ) == ""
    assert (out_dir / "train.txt").read_text(encoding="utf-8") == (
        "./images/train/flight_a__img_001.JPG\n"
    )
    assert (out_dir / "val.txt").read_text(encoding="utf-8") == (
        "./images/val/flight_b__img_002.JPG\n"
    )
    assert yaml.safe_load(data_yaml.read_text(encoding="utf-8")) == {
        "path": "./",
        "train": "train.txt",
        "val": "val.txt",
        "names": {0: "papi_installation"},
    }


def test_build_ultralytics_fails_when_sample_image_is_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Sample image not found"):
        build_ultralytics(
            [{"folder": "flight_a", "file": "missing.JPG", "split": "train"}],
            tmp_path / "raw",
            tmp_path / "labels",
            tmp_path / "cvat",
        )


def test_build_ultralytics_annotations_only_does_not_require_images(tmp_path: Path) -> None:
    labels_dir = tmp_path / "labels"
    out_dir = tmp_path / "cvat"

    (labels_dir / "flight_a").mkdir(parents=True)
    (labels_dir / "flight_a" / "missing.txt").write_text(
        "0 0.500000 0.500000 0.250000 0.250000\n",
        encoding="utf-8",
    )

    build_ultralytics(
        [{"folder": "flight_a", "file": "missing.JPG", "split": "train"}],
        tmp_path / "raw",
        labels_dir,
        out_dir,
        include_images=False,
    )

    assert not (out_dir / "images").exists()
    assert (out_dir / "labels" / "train" / "flight_a__missing.txt").read_text(
        encoding="utf-8"
    ) == "0 0.500000 0.500000 0.250000 0.250000\n"
    assert (out_dir / "train.txt").read_text(encoding="utf-8") == (
        "./images/train/flight_a__missing.JPG\n"
    )


def test_build_ultralytics_accepts_class_name_override(tmp_path: Path) -> None:
    labels_dir = tmp_path / "labels"
    out_dir = tmp_path / "cvat"

    (labels_dir / "flight_a").mkdir(parents=True)
    (labels_dir / "flight_a" / "img_001.txt").write_text(
        "2 0.500000 0.500000 0.250000 0.250000\n",
        encoding="utf-8",
    )

    data_yaml = build_ultralytics(
        [{"folder": "flight_a", "file": "img_001.JPG", "split": "train"}],
        tmp_path / "raw",
        labels_dir,
        out_dir,
        include_images=False,
        class_names={0: "papi_light_red", 1: "papi_light_white"},
    )

    assert yaml.safe_load(data_yaml.read_text(encoding="utf-8"))["names"] == {
        0: "papi_light_red",
        1: "papi_light_white",
    }


def test_build_ultralytics_original_image_name_mode_matches_existing_cvat_frames(
    tmp_path: Path,
) -> None:
    labels_dir = tmp_path / "labels"
    out_dir = tmp_path / "cvat"

    (labels_dir / "flight_a").mkdir(parents=True)
    (labels_dir / "flight_a" / "img_001.txt").write_text(
        "0 0.500000 0.500000 0.250000 0.250000\n",
        encoding="utf-8",
    )

    build_ultralytics(
        [{"folder": "flight_a", "file": "img_001.JPG", "split": "train"}],
        tmp_path / "raw",
        labels_dir,
        out_dir,
        include_images=False,
        image_name_mode="original",
    )

    assert (out_dir / "labels" / "train" / "img_001.txt").read_text(
        encoding="utf-8"
    ) == "0 0.500000 0.500000 0.250000 0.250000\n"
    assert (out_dir / "train.txt").read_text(encoding="utf-8") == (
        "./images/train/img_001.JPG\n"
    )


def test_build_ultralytics_original_image_name_mode_rejects_duplicate_outputs(
    tmp_path: Path,
) -> None:
    labels_dir = tmp_path / "labels"

    for folder in ("flight_a", "flight_b"):
        (labels_dir / folder).mkdir(parents=True)
        (labels_dir / folder / "img_001.txt").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate output label path"):
        build_ultralytics(
            [
                {"folder": "flight_a", "file": "img_001.JPG", "split": "train"},
                {"folder": "flight_b", "file": "img_001.JPG", "split": "train"},
            ],
            tmp_path / "raw",
            labels_dir,
            tmp_path / "cvat",
            include_images=False,
            image_name_mode="original",
        )
