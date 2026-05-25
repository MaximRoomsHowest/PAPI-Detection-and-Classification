"""Per-lamp state tests: at-boundary transition and red-transition-white crossing."""

from __future__ import annotations

import math
from pathlib import Path

import yaml

from papi.global_state import derive_global_state
from papi.lamp_state import compute_lamp_state

REPO_ROOT = Path(__file__).resolve().parents[1]
PAPI_CFG = REPO_ROOT / "configs" / "papi_edny.yaml"


def _load_papi_cfg() -> dict:
    """Compose a flat papi-config dict for runway 06 (matches the pre-refactor structure)."""
    with PAPI_CFG.open("r", encoding="utf-8") as fh:
        airport = yaml.safe_load(fh)
    flat = dict(airport["runways"]["06"]["papi"])
    flat["faa_default_set_angles_deg"] = airport["faa_default_set_angles_deg"]
    flat["transition_half_width_deg"] = airport["transition_half_width_deg"]
    flat["default_alt_wgs84_m"] = airport["default_alt_wgs84_m"]
    return flat


def _camera_at_angle(papi_cfg: dict, light_no: int, elev_deg: float, dist_m: float = 500.0) -> dict:
    """Build a synthetic image-row that places the drone at `elev_deg` above light `light_no` at `dist_m` horizontal distance."""
    light = papi_cfg["light_" + str(light_no)]
    lat = float(light["lat"])
    lon = float(light["lon"])
    lamp_alt = float(papi_cfg["default_alt_wgs84_m"])

    # Place camera `dist_m` due east of the lamp and altitude_diff above it.
    dlon_deg = dist_m / (111_320.0 * math.cos(math.radians(lat)))
    altitude_diff = math.tan(math.radians(elev_deg)) * dist_m

    return {
        "lat": lat,
        "lon": lon + dlon_deg,
        "alt_ellipsoidal_m": lamp_alt + altitude_diff,
    }


def test_lamp_state_at_set_angle_is_transition():
    """Camera placed exactly at light_1's set-angle returns transition for light_1."""
    cfg = _load_papi_cfg()
    set_angle_1 = cfg["faa_default_set_angles_deg"][0]  # 2.50
    row = _camera_at_angle(cfg, light_no=1, elev_deg=set_angle_1)
    lamps, margin = compute_lamp_state(row, cfg)
    assert lamps[0] == "transition", f"lamp 1 at exact set-angle should be transition, got {lamps[0]}"
    assert margin >= 0.0


def test_lamp_state_crossing_red_transition_white():
    """Climbing through light_1's set-angle should produce red -> transition -> white."""
    cfg = _load_papi_cfg()
    set_angle_1 = cfg["faa_default_set_angles_deg"][0]
    half = float(cfg["transition_half_width_deg"])

    below = _camera_at_angle(cfg, light_no=1, elev_deg=set_angle_1 - half - 0.5)
    at = _camera_at_angle(cfg, light_no=1, elev_deg=set_angle_1)
    above = _camera_at_angle(cfg, light_no=1, elev_deg=set_angle_1 + half + 0.5)

    assert compute_lamp_state(below, cfg)[0][0] == "red"
    assert compute_lamp_state(at, cfg)[0][0] == "transition"
    assert compute_lamp_state(above, cfg)[0][0] == "white"


def test_derive_global_state_basic():
    assert derive_global_state(("white", "white", "white", "white")) == "4W"
    assert derive_global_state(("white", "white", "white", "red")) == "3W1R"
    assert derive_global_state(("white", "white", "red", "red")) == "2W2R"
    assert derive_global_state(("white", "red", "red", "red")) == "1W3R"
    assert derive_global_state(("red", "red", "red", "red")) == "4R"
    assert derive_global_state(("white", "transition", "red", "red")) == "TRANSITION"
