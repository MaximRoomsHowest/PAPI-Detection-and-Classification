import math

import app.services.angle as angle_module
import pytest
from app.services.angle import (
    PLAUSIBILITY_MAX_NEAREST_LAMP_M,
    _elevation_from_enu,
    _extract_dji_xmp_pose,
    _geodetic_to_ecef,
    _geodetic_to_enu,
    compute_elevation_angles,
    extract_gps_metadata,
    extract_gps_uncertainty,
    haversine,
    unavailable_angle,
)
from app.services.runways import get_runway

# Angle ranges the data-analysis notebook (haversine method) produced for the
# 461.37 m reference — the ENU method must agree with these to ~0.02 deg.
NOTEBOOK_REFERENCE_RANGES = {
    "papi_06": {"min": 0.6796213080756719, "max": 3.232287681153522},
    "papi_24": {"min": 0.9525530371962151, "max": 4.580270954977426},
}
DATA_ANALYSIS_ASSIGNED_LAMP_ALTITUDE_M = 461.37
DATA_ANALYSIS_DRONE_FLOOR_PROXY_ALTITUDE_M = 464.988

_WGS84_B = 6_378_137.0 * (1.0 - 1.0 / 298.257223563)  # semi-minor axis ~6356752.314


# --- WGS-84 ECEF: known closed-form references ------------------------------

def test_geodetic_to_ecef_known_points():
    x, y, z = _geodetic_to_ecef(0.0, 0.0, 0.0)
    assert (x, y, z) == pytest.approx((6_378_137.0, 0.0, 0.0), abs=1e-3)

    x, y, z = _geodetic_to_ecef(0.0, 90.0, 0.0)
    assert (x, y, z) == pytest.approx((0.0, 6_378_137.0, 0.0), abs=1e-3)

    x, y, z = _geodetic_to_ecef(90.0, 0.0, 0.0)
    assert (x, y, z) == pytest.approx((0.0, 0.0, _WGS84_B), abs=1e-2)


# --- ENU sanity -------------------------------------------------------------

def test_enu_same_point_is_origin():
    e, n, u = _geodetic_to_enu(47.6688, 9.504, 461.37, 47.6688, 9.504, 461.37)
    assert (e, n, u) == pytest.approx((0.0, 0.0, 0.0), abs=1e-6)


def test_enu_straight_up_is_pure_up():
    e, n, u = _geodetic_to_enu(47.6688, 9.504, 561.37, 47.6688, 9.504, 461.37)
    assert e == pytest.approx(0.0, abs=1e-6)
    assert n == pytest.approx(0.0, abs=1e-6)
    assert u == pytest.approx(100.0, abs=1e-3)


def test_elevation_overhead_is_90_degrees():
    runway = get_runway("papi_24")
    mid_lat = sum(light["latitude"] for light in runway["lights"]) / 4
    mid_lon = sum(light["longitude"] for light in runway["lights"]) / 4
    result = compute_elevation_angles(mid_lat, mid_lon, 461.37 + 120.0, "papi_24")
    assert result.elevation_angle_deg == pytest.approx(90.0, abs=0.05)


def test_elevation_from_enu_three_degree_glidepath():
    # 300 m horizontal (north), height = 300*tan(3deg) above -> exactly 3.0 deg.
    horizontal, angle = _elevation_from_enu(0.0, 300.0, 300.0 * math.tan(math.radians(3.0)))
    assert horizontal == pytest.approx(300.0, abs=1e-6)
    assert angle == pytest.approx(3.0, abs=1e-9)


# --- Objective oracle: hand-rolled ENU vs pymap3d ---------------------------

def test_enu_matches_pymap3d_oracle():
    pymap3d = pytest.importorskip("pymap3d")
    ref = (47.6688, 9.504, 461.37)
    samples = [
        (47.667486, 9.500453, 465.147),
        (47.675202, 9.522888, 468.034),
        (47.6700, 9.5100, 500.0),
        (47.6600, 9.4900, 480.0),
    ]
    for lat, lon, alt in samples:
        ours = _geodetic_to_enu(lat, lon, alt, *ref)
        theirs = pymap3d.geodetic2enu(lat, lon, alt, *ref)
        assert ours == pytest.approx(theirs, abs=1e-3)  # sub-mm agreement


# --- Equivalence with the notebook (haversine) within tolerance -------------

def test_compute_matches_notebook_haversine_within_tolerance():
    """ENU and the notebook's haversine+atan2 agree to ~0.01 deg at this scale."""
    drone = (47.667486, 9.500453, 465.147)
    light1 = get_runway("papi_06")["lights"][0]
    haversine_angle = math.degrees(
        math.atan2(
            drone[2] - light1["altitude_m"],
            haversine(drone[0], drone[1], light1["latitude"], light1["longitude"]),
        )
    )

    result = compute_elevation_angles(*drone, "papi_06")
    assert result.angle_available is True
    assert result.angle_source == "metadata"
    assert len(result.per_light_angles) == 4
    assert result.per_light_angles[0].runway_lamp == 1
    # ~0.711 deg in the notebook; ENU must match the haversine result closely.
    assert result.per_light_angles[0].elevation_angle_deg == pytest.approx(haversine_angle, abs=0.02)
    assert result.per_light_angles[0].elevation_angle_deg == pytest.approx(0.711, abs=0.02)


def test_papi_24_first_frame_matches_notebook_edge():
    result = compute_elevation_angles(47.675202, 9.522888, 468.034, "papi_24")
    # Notebook (haversine) gave 0.952553 for lamp 4; ENU agrees within ~0.01 deg.
    assert result.per_light_angles[3].elevation_angle_deg == pytest.approx(0.952553, abs=0.01)


def test_midpoint_angle_is_within_per_lamp_spread():
    result = compute_elevation_angles(47.675202, 9.522888, 485.0, "papi_24")
    per = [light.elevation_angle_deg for light in result.per_light_angles]
    assert min(per) - 0.05 <= result.elevation_angle_deg <= max(per) + 0.05
    assert math.isfinite(result.elevation_angle_deg)


# --- Config + contract guards (unchanged behaviour) -------------------------

def test_haversine_matches_notebook_example_distance():
    assert round(haversine(47.667486, 9.500453, 47.668810, 9.504007), 3) == 304.136


def test_runway_altitudes_use_461_37_reference_height():
    for runway_id in ("papi_06", "papi_24"):
        runway = get_runway(runway_id)
        assert [light["altitude_m"] for light in runway["lights"]] == [DATA_ANALYSIS_ASSIGNED_LAMP_ALTITUDE_M] * 4


def test_papi_06_data_analysis_floor_proxy_is_not_runtime_lamp_height():
    runway = get_runway("papi_06")

    assert [light["altitude_m"] for light in runway["lights"]] == [DATA_ANALYSIS_ASSIGNED_LAMP_ALTITUDE_M] * 4
    assert all(
        light["altitude_m"] != pytest.approx(DATA_ANALYSIS_DRONE_FLOOR_PROXY_ALTITUDE_M)
        for light in runway["lights"]
    )


def test_papi_06_candidate_height_delta_is_material(monkeypatch):
    """The data-analysis drone floor proxy would shift a representative rwy-06 frame by ~0.68 deg."""
    drone = (47.667486, 9.500453, 465.147)
    base_runway = get_runway("papi_06")
    runtime = compute_elevation_angles(*drone, "papi_06")

    def fake_get_runway(runway_id: str):
        if runway_id != "papi_06":
            return get_runway(runway_id)
        return {
            **base_runway,
            "lights": [
                {**light, "altitude_m": DATA_ANALYSIS_DRONE_FLOOR_PROXY_ALTITUDE_M}
                for light in base_runway["lights"]
            ],
        }

    monkeypatch.setattr(angle_module, "get_runway", fake_get_runway)
    floor_proxy = compute_elevation_angles(*drone, "papi_06")

    assert runtime.per_light_angles[0].elevation_angle_deg == pytest.approx(0.711, abs=0.02)
    assert floor_proxy.per_light_angles[0].elevation_angle_deg == pytest.approx(0.0285, abs=0.005)
    assert runtime.elevation_angle_deg - floor_proxy.elevation_angle_deg == pytest.approx(0.679738, abs=0.001)


def test_reference_angle_ranges_from_data_analysis_notebook_are_pinned():
    assert NOTEBOOK_REFERENCE_RANGES["papi_06"]["max"] == 3.232287681153522
    assert NOTEBOOK_REFERENCE_RANGES["papi_24"]["max"] == 4.580270954977426


def test_unavailable_angle_is_explicit():
    result = unavailable_angle("metadata missing")
    assert result.angle_available is False
    assert result.elevation_angle_deg is None
    assert result.per_light_angles == []
    assert result.angle_note == "metadata missing"


# --- RTK altitude: prefer DJI XMP AbsoluteAltitude over non-RTK EXIF ----------

_XMP_SAMPLE = (
    b'<x:xmpmeta xmlns:drone-dji="http://www.dji.com/drone-dji/1.0/" '
    b'drone-dji:GpsLatitude="47.668810" drone-dji:GpsLongitude="9.504007" '
    b'drone-dji:AbsoluteAltitude="+476.20" drone-dji:RelativeAltitude="+15.10" '
    b'drone-dji:RtkFlag="50"></x:xmpmeta>'
)


def test_dji_xmp_pose_parses_attribute_form():
    pose = _extract_dji_xmp_pose(_XMP_SAMPLE)
    assert pose["abs_alt"] == pytest.approx(476.20)
    assert pose["lat"] == pytest.approx(47.668810)
    assert pose["lon"] == pytest.approx(9.504007)
    assert pose["rel_alt"] == pytest.approx(15.10)
    assert pose["rtk_flag"] == 50.0


def test_dji_xmp_pose_parses_element_form():
    raw = (
        b"<drone-dji:AbsoluteAltitude>+480.5</drone-dji:AbsoluteAltitude>"
        b"<drone-dji:GpsLatitude>47.6</drone-dji:GpsLatitude>"
        b"<drone-dji:GpsLongitude>9.5</drone-dji:GpsLongitude>"
    )
    pose = _extract_dji_xmp_pose(raw)
    assert pose["abs_alt"] == pytest.approx(480.5)
    assert pose["lat"] == pytest.approx(47.6)


def test_extract_gps_prefers_rtk_xmp_altitude(tmp_path):
    """When the RTK XMP pose is present it must win over EXIF (the angle-bug fix)."""
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe1" + _XMP_SAMPLE + b"\x00" * 64)
    result = extract_gps_metadata(path)
    assert result is not None
    lat, lon, alt = result
    assert alt == pytest.approx(476.20)  # RTK ellipsoidal AbsoluteAltitude, not EXIF
    assert lat == pytest.approx(47.668810)
    assert lon == pytest.approx(9.504007)


def test_extract_gps_returns_none_without_pose(tmp_path):
    path = tmp_path / "nometa.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 256)
    assert extract_gps_metadata(path) is None


# --- Plausibility: flag a wrong-runway / wrong-datum selection, never block ----

def test_implausible_distance_flags_but_still_returns_angle():
    """A drone over Paris scored against EDNY is geometrically valid but meaningless."""
    result = compute_elevation_angles(48.8566, 2.3522, 500.0, "papi_24")
    # The angle is STILL computed and returned — the warning never withholds it.
    assert result.angle_available is True
    assert result.elevation_angle_deg is not None
    # ...but it is flagged implausible, with a reason and the (huge) distance.
    assert result.plausible is False
    assert result.plausibility_note
    assert result.nearest_lamp_distance_m > PLAUSIBILITY_MAX_NEAREST_LAMP_M
    assert result.nearest_lamp_distance_m > 400_000  # Paris->EDNY is ~540 km


def test_near_runway_fix_is_plausible():
    result = compute_elevation_angles(47.667486, 9.500453, 465.147, "papi_06")
    assert result.plausible is True
    assert result.plausibility_note is None
    # The notebook cross-check distance at this fix is ~300 m — well under the bound.
    assert result.nearest_lamp_distance_m < 1_000


def test_unavailable_angle_defaults_to_plausible_with_no_distance():
    """Back-compat: the not-available path has no geometry to judge."""
    result = unavailable_angle("metadata missing")
    assert result.plausible is True
    assert result.nearest_lamp_distance_m is None
    assert result.elevation_angle_uncertainty_deg is None


# --- RTK uncertainty: a 1-sigma band only when std is supplied ----------------

def test_rtk_std_propagates_to_uncertainty_band():
    result = compute_elevation_angles(
        47.667486, 9.500453, 465.147, "papi_06",
        sigma_horizontal_m=0.02, sigma_vertical_m=0.03,
    )
    band = result.elevation_angle_uncertainty_deg
    assert band is not None
    assert band > 0.0
    # A few cm of RTK std at a few hundred metres baseline is a sub-degree band.
    assert band < 1.0


def test_no_rtk_std_means_no_band():
    result = compute_elevation_angles(47.667486, 9.500453, 465.147, "papi_06")
    assert result.elevation_angle_uncertainty_deg is None


# --- RTK std extraction from DJI XMP ------------------------------------------

_XMP_WITH_RTK_STD = (
    b'<x:xmpmeta xmlns:drone-dji="http://www.dji.com/drone-dji/1.0/" '
    b'drone-dji:GpsLatitude="47.668810" drone-dji:GpsLongitude="9.504007" '
    b'drone-dji:AbsoluteAltitude="+476.20" '
    b'drone-dji:RtkStdLat="0.012" drone-dji:RtkStdLon="0.016" drone-dji:RtkStdHgt="0.025">'
    b"</x:xmpmeta>"
)


def test_dji_xmp_pose_parses_rtk_std():
    pose = _extract_dji_xmp_pose(_XMP_WITH_RTK_STD)
    assert pose["rtk_std_lat"] == pytest.approx(0.012)
    assert pose["rtk_std_lon"] == pytest.approx(0.016)
    assert pose["rtk_std_hgt"] == pytest.approx(0.025)


def test_extract_gps_uncertainty_combines_horizontal(tmp_path):
    path = tmp_path / "rtk.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe1" + _XMP_WITH_RTK_STD + b"\x00" * 64)
    uncertainty = extract_gps_uncertainty(path)
    assert uncertainty is not None
    sigma_h, sigma_v = uncertainty
    assert sigma_h == pytest.approx(math.hypot(0.012, 0.016))
    assert sigma_v == pytest.approx(0.025)


def test_extract_gps_uncertainty_none_without_std(tmp_path):
    path = tmp_path / "nostd.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe1" + _XMP_SAMPLE + b"\x00" * 64)
    assert extract_gps_uncertainty(path) is None
