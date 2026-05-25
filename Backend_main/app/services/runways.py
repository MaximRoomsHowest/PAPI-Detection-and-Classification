from app.validation.schemas import RunwayResponse


RUNWAYS: dict[str, dict] = {
    "papi_06": {
        "id": "papi_06",
        "label": "PAPI 06",
        "lights": [
            {"point": 1, "longitude": 9.504007, "latitude": 47.668810, "altitude_m": 464.988},
            {"point": 2, "longitude": 9.503948, "latitude": 47.668881, "altitude_m": 464.988},
            {"point": 3, "longitude": 9.503888, "latitude": 47.668951, "altitude_m": 464.988},
            {"point": 4, "longitude": 9.503828, "latitude": 47.669021, "altitude_m": 464.988},
        ],
    },
    "papi_24": {
        "id": "papi_24",
        "label": "PAPI 24",
        "lights": [
            {"point": 1, "longitude": 9.518154, "latitude": 47.673521, "altitude_m": 467.609},
            {"point": 2, "longitude": 9.518214, "latitude": 47.673450, "altitude_m": 467.609},
            {"point": 3, "longitude": 9.518274, "latitude": 47.673380, "altitude_m": 467.609},
            {"point": 4, "longitude": 9.518333, "latitude": 47.673309, "altitude_m": 467.609},
        ],
    },
}


def list_runways() -> list[RunwayResponse]:
    return [RunwayResponse(**runway) for runway in RUNWAYS.values()]


def get_runway(runway_id: str) -> dict:
    try:
        return RUNWAYS[runway_id]
    except KeyError as exc:
        raise ValueError(f"Unknown runway_id: {runway_id}") from exc
