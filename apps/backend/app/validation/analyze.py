from fastapi import HTTPException

# Plausible physical ranges for manually supplied drone telemetry. Out-of-range
# coordinates used to silently flow into the elevation-angle math and produce
# nonsense results (audit IMP-BE-10 / IMP-SEC-5), so they are rejected up front.
#   - latitude/longitude: full WGS84 degree ranges.
#   - altitude: from below the lowest land surface (Dead Sea, ~-430 m) up to
#     well above any legal drone ceiling, giving slack without accepting garbage.
LATITUDE_MIN_DEG = -90.0
LATITUDE_MAX_DEG = 90.0
LONGITUDE_MIN_DEG = -180.0
LONGITUDE_MAX_DEG = 180.0
ALTITUDE_MIN_M = -500.0
ALTITUDE_MAX_M = 20000.0


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
    if not LATITUDE_MIN_DEG <= latitude <= LATITUDE_MAX_DEG:
        raise HTTPException(status_code=400, detail="drone_latitude must be between -90 and 90 degrees.")
    if not LONGITUDE_MIN_DEG <= longitude <= LONGITUDE_MAX_DEG:
        raise HTTPException(status_code=400, detail="drone_longitude must be between -180 and 180 degrees.")
    if not ALTITUDE_MIN_M <= altitude_m <= ALTITUDE_MAX_M:
        raise HTTPException(status_code=400, detail="drone_altitude_m must be between -500 and 20000 metres.")
    return latitude, longitude, altitude_m
