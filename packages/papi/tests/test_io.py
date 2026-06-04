"""YOLO label + data.yaml writer behaviour (audit IMP-ML-2 follow-up).

``write_data_yaml`` is parameterised by class names so the descriptor matches the
labels it ships with: installation-level by default, red/white when asked.
"""

import yaml
from papi.io import (
    LAMP_STATE_CLASS_NAMES,
    write_data_yaml,
    write_yolo_label,
    write_yolo_labels,
)


def test_write_data_yaml_defaults_to_installation_taxonomy(tmp_path):
    out = tmp_path / "data.yaml"
    write_data_yaml(out)
    text = out.read_text(encoding="utf-8")
    assert "0: papi_installation" in text
    # The single-class installation default must not leak lamp-state names.
    assert "papi_light_red" not in text


def test_write_data_yaml_emits_lamp_state_classes_when_requested(tmp_path):
    out = tmp_path / "data.yaml"
    write_data_yaml(out, LAMP_STATE_CLASS_NAMES)
    text = out.read_text(encoding="utf-8")
    assert "0: papi_light_red" in text
    assert "1: papi_light_white" in text
    assert "papi_installation" not in text


def test_write_data_yaml_is_valid_parseable_yaml(tmp_path):
    out = tmp_path / "data.yaml"
    write_data_yaml(out, LAMP_STATE_CLASS_NAMES)
    parsed = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert parsed["names"] == {0: "papi_light_red", 1: "papi_light_white"}
    assert parsed["train"] == "data/labels/auto"


def test_write_data_yaml_includes_all_split_and_path_keys(tmp_path):
    """The descriptor must carry path/train/val/test, not just train -- a trainer that
    can't resolve val/test silently skips evaluation."""
    out = tmp_path / "data.yaml"
    write_data_yaml(out)
    parsed = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert parsed["path"] == "../"
    assert parsed["train"] == "data/labels/auto"
    assert parsed["val"] == "data/labels/auto"
    assert parsed["test"] == "data/labels/auto"


def test_write_yolo_labels_normalizes_bbox_to_centre_width_height(tmp_path):
    """xyxy pixel bbox -> normalised cx/cy/w/h at 6 decimals. A (10,20)-(30,60) box in a
    100x200 image is centred at (0.2, 0.2) and is 0.2 wide x 0.2 tall."""
    out = tmp_path / "frame.txt"
    write_yolo_labels(out, [(0, (10.0, 20.0, 30.0, 60.0))], image_width=100, image_height=200)
    assert out.read_text(encoding="utf-8") == "0 0.200000 0.200000 0.200000 0.200000\n"


def test_write_yolo_label_matches_single_row_write_yolo_labels(tmp_path):
    """The single-label convenience wrapper produces byte-identical output to the
    list form with one row."""
    single = tmp_path / "single.txt"
    multi = tmp_path / "multi.txt"
    write_yolo_label(single, 1, (0.0, 0.0, 50.0, 100.0), image_width=100, image_height=100)
    write_yolo_labels(multi, [(1, (0.0, 0.0, 50.0, 100.0))], image_width=100, image_height=100)
    assert single.read_text(encoding="utf-8") == multi.read_text(encoding="utf-8")


def test_write_yolo_labels_empty_produces_empty_file(tmp_path):
    """A frame with no detections is a valid YOLO background image: an EMPTY file, not a
    lone newline (which some loaders read as a malformed row)."""
    out = tmp_path / "background.txt"
    write_yolo_labels(out, [], image_width=100, image_height=100)
    assert out.read_text(encoding="utf-8") == ""
