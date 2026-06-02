import { describe, expect, it } from 'vitest'
import { detectTransitionAngle } from './insightsTransforms'

// detectTransitionAngle estimates the angle where a PAPI lamp switches red -> white
// (its commissioned set angle) as the midpoint of the first red|transition -> white
// crossing in the angle-sorted samples. Pure detection from real classified states.

describe('detectTransitionAngle', () => {
  it('returns the midpoint of a red -> white crossing', () => {
    const points = [
      { angle: 2.0, state: 'red' },
      { angle: 2.5, state: 'red' },
      { angle: 2.6, state: 'white' },
      { angle: 3.0, state: 'white' },
    ]
    expect(detectTransitionAngle(points)).toBeCloseTo(2.55, 5)
  })

  it('uses a transition-labelled sample as the lower bound of the crossing', () => {
    const points = [
      { angle: 2.0, state: 'red' },
      { angle: 2.4, state: 'transition' },
      { angle: 2.6, state: 'white' },
    ]
    expect(detectTransitionAngle(points)).toBeCloseTo(2.5, 5)
  })

  it('ignores obscured samples when locating the crossing', () => {
    const points = [
      { angle: 2.0, state: 'obscured' },
      { angle: 2.1, state: 'red' },
      { angle: 2.5, state: 'white' },
    ]
    expect(detectTransitionAngle(points)).toBeCloseTo(2.3, 5)
  })

  it('sorts unordered samples before detecting', () => {
    const points = [
      { angle: 3.0, state: 'white' },
      { angle: 2.0, state: 'red' },
      { angle: 2.6, state: 'white' },
      { angle: 2.5, state: 'red' },
    ]
    expect(detectTransitionAngle(points)).toBeCloseTo(2.55, 5)
  })

  it('returns null when the lamp never goes white', () => {
    expect(detectTransitionAngle([
      { angle: 2.0, state: 'red' },
      { angle: 3.0, state: 'red' },
    ])).toBeNull()
  })

  it('returns null when the lamp is already white throughout', () => {
    expect(detectTransitionAngle([
      { angle: 2.0, state: 'white' },
      { angle: 3.0, state: 'white' },
    ])).toBeNull()
  })

  it('returns null for empty or missing input', () => {
    expect(detectTransitionAngle([])).toBeNull()
    expect(detectTransitionAngle(undefined)).toBeNull()
  })
})
