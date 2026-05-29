import { describe, it, expect } from 'vitest'

import { validateDroneMetadata } from './validation.js'

const blank = { droneLatitude: '', droneLongitude: '', droneAltitudeM: '' }

describe('validateDroneMetadata', () => {
  it('treats all-empty metadata as valid (optional, enforced server-side)', () => {
    expect(validateDroneMetadata(blank)).toEqual({ valid: true, errors: {} })
  })

  it('accepts in-range values', () => {
    const result = validateDroneMetadata({
      droneLatitude: '47.67',
      droneLongitude: '9.5',
      droneAltitudeM: '466',
    })
    expect(result.valid).toBe(true)
  })

  it('flags out-of-range latitude', () => {
    const result = validateDroneMetadata({ ...blank, droneLatitude: '999' })
    expect(result.valid).toBe(false)
    expect(result.errors.droneLatitude).toMatch(/between -90 and 90/)
  })

  it('flags out-of-range longitude', () => {
    const result = validateDroneMetadata({ ...blank, droneLongitude: '-200' })
    expect(result.valid).toBe(false)
    expect(result.errors.droneLongitude).toMatch(/between -180 and 180/)
  })

  it('flags non-numeric input', () => {
    const result = validateDroneMetadata({ ...blank, droneAltitudeM: 'abc' })
    expect(result.valid).toBe(false)
    expect(result.errors.droneAltitudeM).toMatch(/must be a number/)
  })
})
