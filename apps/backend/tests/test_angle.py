from app.services.angle import compute_elevation_angles, haversine, unavailable_angle


def test_haversine_matches_notebook_example_distance():
    distance = haversine(47.667486, 9.500453, 47.668810, 9.504007)
    assert round(distance, 3) == 304.136


def test_compute_elevation_angle_matches_notebook_example():
    result = compute_elevation_angles(
        drone_latitude=47.667486,
        drone_longitude=9.500453,
        drone_altitude_m=465.147,
        runway_id="papi_06",
    )

    assert result.angle_available is True
    assert result.angle_source == "metadata"
    assert len(result.per_light_angles) == 4
    assert result.per_light_angles[0].runway_lamp == 1
    assert result.per_light_angles[0].distance_m == 304.136
    assert result.per_light_angles[0].elevation_angle_deg == 0.029954
    assert result.elevation_angle_deg == 0.029923


def test_unavailable_angle_is_explicit():
    result = unavailable_angle("metadata missing")

    assert result.angle_available is False
    assert result.elevation_angle_deg is None
    assert result.per_light_angles == []
    assert result.angle_note == "metadata missing"
