from fastapi import HTTPException


def parse_manual_drone_metadata(
    latitude: float | None,
    longitude: float | None,
    altitude_m: float | None,
) -> tuple[float, float, float] | None:
    values = (latitude, longitude, altitude_m)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise HTTPException(
            status_code=400,
            detail="Provide drone_latitude, drone_longitude, and drone_altitude_m together.",
        )
    return latitude, longitude, altitude_m

