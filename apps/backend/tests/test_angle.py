from app.services.angle import compute_elevation_angles, haversine, unavailable_angle
from app.services.runways import get_runway


def test_haversine_matches_notebook_example_distance():
    distance = haversine(47.667486, 9.500453, 47.668810, 9.504007)
    assert round(distance, 3) == 304.136


def test_compute_elevation_angle_matches_notebook_example():
    """Cross-check the haversine + atan2 against the data-analysis notebook.

    The expected elevation angle is derived rather than pinned to a magic
    number because the underlying lamp altitude moved when runways.py
    switched to loading from configs/papi_edny.yaml (audit C4). The earlier
    pinned value (0.029954) was computed against a placeholder lamp altitude
    of 464.988 m whose provenance was unclear; the YAML's documented field
    elevation (465.0 m WGS84) is now the canonical input. The 12 mm
    difference shifts the angle by ~0.002 deg at this standoff.
    """
    import math

    drone_alt = 465.147
    runway = get_runway("papi_06")
    light1 = runway["lights"][0]
    expected_distance = round(
        haversine(47.667486, 9.500453, light1["latitude"], light1["longitude"]),
        3,
    )
    expected_angle = round(
        math.degrees(
            math.atan2(drone_alt - light1["altitude_m"], expected_distance)
        ),
        6,
    )

    result = compute_elevation_angles(
        drone_latitude=47.667486,
        drone_longitude=9.500453,
        drone_altitude_m=drone_alt,
        runway_id="papi_06",
    )

    assert result.angle_available is True
    assert result.angle_source == "metadata"
    assert len(result.per_light_angles) == 4
    assert result.per_light_angles[0].runway_lamp == 1
    assert result.per_light_angles[0].distance_m == expected_distance
    assert result.per_light_angles[0].elevation_angle_deg == expected_angle


def test_unavailable_angle_is_explicit():
    result = unavailable_angle("metadata missing")

    assert result.angle_available is False
    assert result.elevation_angle_deg is None
    assert result.per_light_angles == []
    assert result.angle_note == "metadata missing"
