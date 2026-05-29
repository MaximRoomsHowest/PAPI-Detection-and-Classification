// Client-side range check on the drone metadata (audit IMP-FE-5) so an obviously
// invalid value fails fast in the UI instead of producing a nonsense angle or a
// backend 422 mid-demo. Empty fields are allowed here — the all-or-none rule and
// the authoritative bounds are still enforced server-side. Ranges match the
// backend validator (IMP-BE-10).
//
// Extracted from App.jsx so it is unit-testable without importing the whole SPA
// (a small first step on the monolith split, IMP-FE-20 / IMP-FE-12).

export function validateDroneMetadata(metadata) {
  const errors = {}
  const checkRange = (field, value, min, max, label) => {
    if (value === '' || value == null) return
    const num = Number(value)
    if (!Number.isFinite(num)) {
      errors[field] = `${label} must be a number.`
    } else if (num < min || num > max) {
      errors[field] = `${label} must be between ${min} and ${max}.`
    }
  }
  checkRange('droneLatitude', metadata.droneLatitude, -90, 90, 'Latitude')
  checkRange('droneLongitude', metadata.droneLongitude, -180, 180, 'Longitude')
  checkRange('droneAltitudeM', metadata.droneAltitudeM, -500, 20000, 'Altitude (m)')
  return { valid: Object.keys(errors).length === 0, errors }
}
