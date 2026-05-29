"""YOLO label + data.yaml writer behaviour (audit IMP-ML-2 follow-up).

``write_data_yaml`` is parameterised by class names so the descriptor matches the
labels it ships with: installation-level by default, red/white when asked.
"""

import yaml
from papi.io import LAMP_STATE_CLASS_NAMES, write_data_yaml


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
