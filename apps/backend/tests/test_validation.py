import pytest
from app.validation.analyze import parse_manual_drone_metadata
from fastapi import HTTPException


def test_parse_manual_drone_metadata_accepts_empty_metadata():
    assert parse_manual_drone_metadata(None, None, None) is None


def test_parse_manual_drone_metadata_requires_all_values():
    with pytest.raises(HTTPException):
        parse_manual_drone_metadata(47.0, None, 465.0)


def test_parse_manual_drone_metadata_returns_coordinate_tuple():
    assert parse_manual_drone_metadata(47.0, 9.0, 465.0) == (47.0, 9.0, 465.0)


@pytest.mark.parametrize(
    "latitude, longitude, altitude_m",
    [
        pytest.param(91.0, 9.0, 465.0, id="latitude-above-90"),
        pytest.param(-91.0, 9.0, 465.0, id="latitude-below-minus-90"),
        pytest.param(47.0, 181.0, 465.0, id="longitude-above-180"),
        pytest.param(47.0, -181.0, 465.0, id="longitude-below-minus-180"),
        pytest.param(47.0, 9.0, 20001.0, id="altitude-above-max"),
        pytest.param(47.0, 9.0, -501.0, id="altitude-below-min"),
    ],
)
def test_parse_manual_drone_metadata_rejects_out_of_range(latitude, longitude, altitude_m):
    """Audit IMP-BE-10 / IMP-SEC-5: out-of-range telemetry is rejected with 400 before it
    can reach the elevation-angle math -- for every coordinate, not just latitude."""
    with pytest.raises(HTTPException) as exc_info:
        parse_manual_drone_metadata(latitude, longitude, altitude_m)
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "latitude, longitude, altitude_m",
    [
        pytest.param(90.0, 180.0, 20000.0, id="upper-boundaries"),
        pytest.param(-90.0, -180.0, -500.0, id="lower-boundaries"),
    ],
)
def test_parse_manual_drone_metadata_accepts_boundaries(latitude, longitude, altitude_m):
    """The min/max bounds use inclusive (<=) comparisons, so the exact edges are accepted."""
    assert parse_manual_drone_metadata(latitude, longitude, altitude_m) == (
        latitude,
        longitude,
        altitude_m,
    )

