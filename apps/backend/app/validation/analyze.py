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
    # Range validation (audit IMP-BE-10 / IMP-SEC-5): out-of-range coordinates used
    # to silently flow into the angle math and produce nonsense elevation angles.
    if not -90.0 <= latitude <= 90.0:
        raise HTTPException(status_code=400, detail="drone_latitude must be between -90 and 90 degrees.")
    if not -180.0 <= longitude <= 180.0:
        raise HTTPException(status_code=400, detail="drone_longitude must be between -180 and 180 degrees.")
    if not -500.0 <= altitude_m <= 20000.0:
        raise HTTPException(status_code=400, detail="drone_altitude_m must be between -500 and 20000 metres.")
    return latitude, longitude, altitude_m

