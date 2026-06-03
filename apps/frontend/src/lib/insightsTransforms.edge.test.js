/**
 * Edge-branch tests for insightsTransforms.js that complement (do not overlap
 * with) the existing insightsTransforms.test.js. These pin the subtler "no real
 * data / unusual input" paths the charts rely on to avoid fabricating series:
 *
 *   - resolveAngle keeps a legitimate 0deg per-light angle (`??`, not `||`) and
 *     returns null when neither per-light nor frame-level angle is finite.
 *   - angleVsStateSeries drops lamp indexes outside 1..4 and derives the
 *     `log <id8>` label fallback when there's no original_filename.
 *   - perLightStateSeries never adds a stray bucket key for an unexpected state
 *     (the `!== undefined` allow-list guard).
 *   - confidenceValues tolerates a missing (undefined) results array.
 *
 * The existing file already covers the happy paths, the all-empty buckets, the
 * unknown-vs-obscured tier split, and the percent rounding, so we don't repeat
 * those here.
 */

import { describe, it, expect } from 'vitest'

import {
  resolveAngle,
  angleVsStateSeries,
  perLightStateSeries,
  confidenceValues,
} from './insightsTransforms.js'

describe('resolveAngle — zero-angle and non-finite edges', () => {
  it('keeps a legitimate 0 degree per-light angle instead of falling through', () => {
    const angle = {
      angle_available: true,
      elevation_angle_deg: 9, // frame-level differs; must NOT be used
      per_light_angles: [{ runway_lamp: 1, elevation_angle_deg: 0 }],
    }
    expect(resolveAngle(angle, 1)).toBe(0)
  })

  it('returns null when neither per-light nor frame-level angle is finite', () => {
    const angle = { angle_available: true, elevation_angle_deg: null, per_light_angles: [] }
    expect(resolveAngle(angle, 1)).toBeNull()
  })
})

describe('angleVsStateSeries — out-of-range lamps and label fallback', () => {
  it('ignores lamp indexes outside 1..4', () => {
    const results = [
      {
        angle: { angle_available: true, elevation_angle_deg: 2.0 },
        lamps: [
          { index: 0, state: 'white', confidence: 0.5 },
          { index: 5, state: 'red', confidence: 0.5 },
        ],
      },
    ]
    const series = angleVsStateSeries(results)
    expect(series.every((s) => s.points.length === 0)).toBe(true)
  })

  it('labels a point with "log <first 8 of log_id>" when there is no filename', () => {
    const results = [
      {
        angle: { angle_available: true, elevation_angle_deg: 3.0 },
        log_id: 'abcdef1234567890',
        // no original_filename
        lamps: [{ index: 1, state: 'white', confidence: 0.8 }],
      },
    ]
    expect(angleVsStateSeries(results)[0].points[0].label).toBe('log abcdef12')
  })

  it('falls back to an empty label when neither filename nor log_id exists', () => {
    const results = [
      {
        angle: { angle_available: true, elevation_angle_deg: 3.0 },
        lamps: [{ index: 1, state: 'white', confidence: 0.8 }],
      },
    ]
    expect(angleVsStateSeries(results)[0].points[0].label).toBe('')
  })
})

describe('perLightStateSeries — unexpected-state guard', () => {
  it('never creates a stray bucket key for an out-of-allow-list state', () => {
    const bucket = perLightStateSeries([{ lamps: [{ index: 1, state: 'banana' }] }])[0]
    expect(Object.keys(bucket).sort()).toEqual(
      ['obscured', 'red', 'transition', 'unknown', 'white'].sort(),
    )
    expect(bucket).not.toHaveProperty('banana')
    // and the bucket stays fully zeroed
    expect(Object.values(bucket).every((v) => v === 0)).toBe(true)
  })
})

describe('confidenceValues — missing results array', () => {
  it('returns an empty array when given undefined', () => {
    expect(confidenceValues(undefined)).toEqual([])
  })
})
