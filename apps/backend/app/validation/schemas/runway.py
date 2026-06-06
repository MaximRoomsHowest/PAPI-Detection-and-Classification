from pydantic import BaseModel, Field, model_validator


class RunwayLight(BaseModel):
    point: int
    latitude: float
    longitude: float
    altitude_m: float


class RunwayResponse(BaseModel):
    id: str
    label: str
    lights: list[RunwayLight]
    # Display-only metadata + provenance. ``source`` is "config" for the built-in
    # surveyed runways from configs/papi_edny.yaml and "custom" for ones registered
    # at runtime via POST /api/runways. All optional/defaulted so the existing
    # built-in dicts (which omit these keys) still validate unchanged.
    airport: str | None = None
    designation: str | None = None
    source: str = "config"


class RunwayLightInput(BaseModel):
    """One PAPI lamp position in a create-runway request, WGS-84 and range-checked
    so a typo can't push a nonsense coordinate into the ENU elevation-angle solver.
    Lat/lon bounds match the drone-GPS validation in services/angle.py; the altitude
    ceiling here (15,000 m) is an independent, tighter lamp bound — drone GPS allows
    up to ALTITUDE_MAX_M = 20,000 m — so the two are intentionally not coupled."""

    point: int = Field(ge=1, le=4)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    altitude_m: float = Field(ge=-500.0, le=15_000.0)


class RunwayCreate(BaseModel):
    """Body for POST /api/runways — registers a runway the model can actually score
    against. The four lamp positions are required because the elevation-angle solver
    needs per-lamp WGS-84 geometry; without distinct coordinates the per-lamp angles
    would be meaningless."""

    label: str = Field(min_length=1, max_length=120)
    id: str | None = Field(default=None, max_length=80)
    airport: str | None = Field(default=None, max_length=120)
    designation: str | None = Field(default=None, max_length=40)
    lights: list[RunwayLightInput]

    @model_validator(mode="after")
    def _check_lights(self) -> "RunwayCreate":
        # Reject a blank-after-strip label and persist the stripped value: min_length=1
        # still admits "   ", which the store later strips to "" so the runway silently
        # vanishes on the next reload (audit). Stripping here makes both paths agree.
        stripped = self.label.strip()
        if not stripped:
            raise ValueError("Runway label must not be blank.")
        self.label = stripped
        if len(self.lights) != 4:
            raise ValueError("A runway must have exactly 4 PAPI lamps.")
        if sorted(light.point for light in self.lights) != [1, 2, 3, 4]:
            raise ValueError("Lamp points must be 1, 2, 3 and 4 (one of each).")
        # Reject degenerate geometry: identical lamp coordinates make the per-lamp
        # elevation angles meaningless (audit). ~1e-6 deg rounding (~0.1 m).
        positions = {(round(lamp.latitude, 6), round(lamp.longitude, 6)) for lamp in self.lights}
        if len(positions) < 4:
            raise ValueError("Lamp coordinates must be 4 distinct positions.")
        return self
