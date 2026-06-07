import { describe, expect, it } from 'vitest'
import {
  angleBrightnessSeries,
  angleVsStateSeries,
  confidenceValues,
  elevationOverFrameSeries,
  perLightStateSeries,
  resolveAngle,
  transitionCountSeries,
} from './insightsTransforms'

const result = ({ available = true, perLight = [], global = 3.0, lamps = [] }) => ({
  original_filename: 'frame.jpg',
  angle: {
    angle_available: available,
    elevation_angle_deg: global,
    per_light_angles: perLight,
  },
  lamps,
})

describe('resolveAngle', () => {
  it('returns null when angle is unavailable', () => {
    expect(resolveAngle({ angle_available: false }, 1)).toBeNull()
    expect(resolveAngle(null, 1)).toBeNull()
  })

  it('prefers the per-light angle, falls back to the global angle', () => {
    const angle = {
      angle_available: true,
      elevation_angle_deg: 3.0,
      per_light_angles: [{ runway_lamp: 2, elevation_angle_deg: 2.61 }],
    }
    expect(resolveAngle(angle, 2)).toBe(2.61)
    expect(resolveAngle(angle, 1)).toBe(3.0) // no per-light entry -> global
  })
})

describe('angleVsStateSeries', () => {
  it('returns four empty light series for no input', () => {
    const series = angleVsStateSeries([])
    expect(series).toHaveLength(4)
    expect(series.every((lamp) => lamp.points.length === 0)).toBe(true)
    expect(series.map((lamp) => lamp.lampIndex)).toEqual([1, 2, 3, 4])
  })

  it('skips results without available angle metadata', () => {
    const series = angleVsStateSeries([
      result({ available: false, lamps: [{ index: 1, state: 'white', confidence: 0.9 }] }),
    ])
    expect(series.every((lamp) => lamp.points.length === 0)).toBe(true)
  })

  it('skips unknown lamp states but keeps red/transition/white', () => {
    const series = angleVsStateSeries([
      result({
        lamps: [
          { index: 1, state: 'white', confidence: 0.95 },
          { index: 2, state: 'unknown', confidence: 0.4 },
          { index: 3, state: 'transition', confidence: 0.7 },
        ],
      }),
    ])
    expect(series[0].points).toHaveLength(1) // light 1 white
    expect(series[0].points[0].stateNum).toBe(2)
    expect(series[0].points[0].confidence).toBe(95) // 0.95 -> 95%
    expect(series[1].points).toHaveLength(0) // light 2 unknown skipped
    expect(series[2].points[0].stateNum).toBe(1) // transition
  })

  it('includes obscured lamps on their own tier (-1) so non-detections are visible', () => {
    const series = angleVsStateSeries([
      result({
        lamps: [
          { index: 1, state: 'obscured', confidence: 0 },
          { index: 2, state: 'unknown', confidence: 0 },
        ],
      }),
    ])
    expect(series[0].points).toHaveLength(1) // light 1 obscured -> plotted
    expect(series[0].points[0].stateNum).toBe(-1)
    expect(series[0].points[0].state).toBe('obscured')
    expect(series[1].points).toHaveLength(0) // light 2 unknown -> still skipped
  })

  it('uses per-light angles per lamp and sorts points by angle', () => {
    const series = angleVsStateSeries([
      result({
        global: 3.0,
        perLight: [{ runway_lamp: 1, elevation_angle_deg: 3.4 }],
        lamps: [{ index: 1, state: 'white', confidence: 0.9 }],
      }),
      result({
        global: 2.4,
        perLight: [{ runway_lamp: 1, elevation_angle_deg: 2.2 }],
        lamps: [{ index: 1, state: 'red', confidence: 0.88 }],
      }),
    ])
    expect(series[0].points.map((point) => point.angle)).toEqual([2.2, 3.4])
    expect(series[0].points[0].state).toBe('red')
  })

  it('builds a per-lamp sweep from a per-frame angle_track (video telemetry path)', () => {
    const series = angleVsStateSeries([
      {
        original_filename: 'clip.mp4',
        // A single aggregated angle is also present but MUST be ignored in favour
        // of the richer per-frame track.
        angle: { angle_available: true, elevation_angle_deg: 9.9, per_light_angles: [] },
        lamps: [{ index: 1, state: 'white', confidence: 0.9 }],
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.82 }] },
          { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.85 }] },
          { frame_index: 3, elevation_angle_deg: 3.5, lamps: [{ index: 1, state: 'white', confidence: 0.86 }] },
        ],
      },
    ])
    // Four sweep points for lamp 1 from the track — not a single aggregated point,
    // and never the 9.9 from the ignored aggregate angle.
    expect(series[0].points.map((point) => point.angle)).toEqual([2.0, 2.5, 3.0, 3.5])
    expect(series[0].points.map((point) => point.state)).toEqual(['red', 'red', 'white', 'white'])
    // The red->white crossing is the midpoint of the 2.5 -> 3.0 step.
    expect(series[0].transitionAngle).toBeCloseTo(2.75, 5)
  })

  it('falls back to the single aggregated point when angle_track is empty', () => {
    const series = angleVsStateSeries([
      result({ global: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.9 }] }),
    ])
    expect(series[0].points).toHaveLength(1)
    expect(series[0].points[0].angle).toBe(3.0)
  })
})

describe('angleBrightnessSeries', () => {
  it('builds client-style per-lamp brightness curves and marks the transition angle', () => {
    const series = angleBrightnessSeries([
      {
        original_filename: 'clip.mp4',
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.18 }] },
          { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.34 }] },
          { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.72 }] },
        ],
      },
    ])

    expect(series).toHaveLength(4)
    expect(series[0].points.map((point) => point.brightness)).toEqual([18, 34, 72])
    expect(series[0].threshold).toBe(25)
    expect(series[0].transitionAngle).toBeCloseTo(2.75, 5)
  })

  it('returns a null transition angle when the lamp never crosses (no fabricated fallback)', () => {
    const series = angleBrightnessSeries([
      {
        original_filename: 'clip.mp4',
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 1.0, lamps: [{ index: 4, state: 'red', confidence: 0.1 }] },
          { frame_index: 1, elevation_angle_deg: 2.0, lamps: [{ index: 4, state: 'red', confidence: 0.4 }] },
        ],
      },
    ])

    // The lamp stays red throughout: no genuine red<->white crossing, so no marker.
    // (Previously this fabricated a 25%-confidence-threshold crossing at 1.5°.)
    expect(series[3].transitionAngle).toBeNull()
  })
})

describe('elevationOverFrameSeries', () => {
  it('returns no series when no result carries a per-frame angle track', () => {
    expect(elevationOverFrameSeries([])).toEqual([])
    expect(elevationOverFrameSeries([result({ lamps: [{ index: 1, state: 'white', confidence: 0.9 }] })])).toEqual([])
  })

  it('builds one (frame, angle) line per tracked result, skipping non-finite samples', () => {
    const series = elevationOverFrameSeries([
      {
        original_filename: 'clip.mp4',
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0 },
          { frame_index: 1, elevation_angle_deg: null }, // dropped
          { frame_index: 2, elevation_angle_deg: 3.0 },
        ],
      },
    ])
    expect(series).toHaveLength(1)
    expect(series[0].label).toBe('clip.mp4')
    expect(series[0].frames).toEqual([0, 2])
    expect(series[0].angles).toEqual([2.0, 3.0])
  })
})

describe('transitionCountSeries', () => {
  const event = (lampIndex) => ({
    lamp_index: lampIndex,
    from_state: 'white',
    to_state: 'red',
    frame_index: 10,
  })

  it('returns zeros for no transitions', () => {
    expect(transitionCountSeries([])).toEqual({ lamps: [1, 2, 3, 4], counts: [0, 0, 0, 0] })
    expect(transitionCountSeries(undefined).counts).toEqual([0, 0, 0, 0])
  })

  it('counts per light index and ignores out-of-range indices', () => {
    expect(transitionCountSeries([event(1), event(1), event(3), event(4), event(4), event(4)]).counts).toEqual([
      2, 0, 1, 3,
    ])
    expect(transitionCountSeries([event(0), event(5), event(2)]).counts).toEqual([0, 1, 0, 0])
  })
})

describe('perLightStateSeries', () => {
  const resultWith = (lamps) => ({ lamps })

  it('returns four zeroed light buckets for no input', () => {
    const series = perLightStateSeries([])
    expect(series).toHaveLength(4)
    expect(series[0]).toEqual({ white: 0, red: 0, transition: 0, obscured: 0, unknown: 0 })
  })

  it('counts states per light index across results', () => {
    const series = perLightStateSeries([
      resultWith([
        { index: 1, state: 'white', confidence: 0.9 },
        { index: 2, state: 'red', confidence: 0.8 },
      ]),
      resultWith([
        { index: 1, state: 'white', confidence: 0.95 },
        { index: 2, state: 'transition', confidence: 0.7 },
      ]),
    ])
    expect(series[0].white).toBe(2)
    expect(series[1].red).toBe(1)
    expect(series[1].transition).toBe(1)
  })

  it('ignores lamp indices outside 1..4', () => {
    const series = perLightStateSeries([resultWith([{ index: 9, state: 'white', confidence: 0.5 }])])
    expect(series.every((bucket) => bucket.white === 0)).toBe(true)
  })
})

describe('confidenceValues', () => {
  const resultWith = (lamps) => ({ lamps })

  it('collects per-lamp confidences as percentages', () => {
    const values = confidenceValues([
      resultWith([
        { index: 1, state: 'white', confidence: 0.9 },
        { index: 2, state: 'red', confidence: 0.82 },
      ]),
    ])
    expect(values).toEqual([90, 82])
  })

  it('skips non-finite and zero (undetected) confidences', () => {
    const values = confidenceValues([
      resultWith([
        { index: 1, state: 'white', confidence: undefined },
        { index: 2, state: 'unknown', confidence: 0 },
        { index: 3, state: 'red', confidence: 0.7 },
      ]),
    ])
    expect(values).toEqual([70])
  })
})
