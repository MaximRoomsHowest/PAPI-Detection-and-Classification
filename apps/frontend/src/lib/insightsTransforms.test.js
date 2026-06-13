import { describe, expect, it } from 'vitest'
import {
  angleVsStateSeries,
  confidenceValues,
  elevationOverFrameSeries,
  perLightStateSeries,
  resolveAngle,
  stateBandSeries,
  stableTransitionEvents,
  summarizeSession,
  transitionAngleSummary,
  transitionCsv,
  transitionFlickerStatus,
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

// The angle-vs-state transform's own bidirectional/no-fabrication behaviour is
// covered by detectTransitionAngle (angleTransition.test.js) + the angleVsStateSeries
// block above.

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

describe('transitionAngleSummary', () => {
  const sweepResult = {
    original_filename: 'clip.mp4',
    angle_track: [
      { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
      { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.82 }] },
      { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.85 }] },
      { frame_index: 3, elevation_angle_deg: 3.5, lamps: [{ index: 1, state: 'white', confidence: 0.86 }] },
    ],
    transitions: [
      { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 1, elevation_angle_deg: 2.5 },
      { lamp_index: 1, from_state: 'white', to_state: 'red', frame_index: 2, elevation_angle_deg: 2.75 },
      { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 3, elevation_angle_deg: 3.0 },
      // Out-of-range lamp index never lands in a bucket.
      { lamp_index: 7, from_state: 'red', to_state: 'white', frame_index: 3, elevation_angle_deg: 3.1 },
    ],
  }

  it('combines the settled crossing angle with the stabilized flip band per light', () => {
    const summary = transitionAngleSummary([sweepResult])
    expect(summary).toHaveLength(4)
    // settledAngle follows the same stabilized event the table/CSV show.
    expect(summary[0].settledAngle).toBeCloseTo(3.0, 5)
    expect(summary[0].bandMin).toBeCloseTo(3.0, 5)
    expect(summary[0].bandMax).toBeCloseTo(3.0, 5)
    expect(summary[0].flips).toBe(1)
  })

  it('reports null settled angle and empty band for a light that never crossed', () => {
    const summary = transitionAngleSummary([sweepResult])
    expect(summary[1]).toEqual({ lampIndex: 2, settledAngle: null, bandMin: null, bandMax: null, flips: 0 })
  })

  it('handles no input', () => {
    const summary = transitionAngleSummary([])
    expect(summary.every((entry) => entry.settledAngle === null && entry.flips === 0)).toBe(true)
  })

  it('does not fabricate a settled angle from angle_track when backend transitions are authoritative and empty', () => {
    const summary = transitionAngleSummary([
      {
        transition_method: 'tracking',
        transitions: [],
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
          { frame_index: 3, elevation_angle_deg: 3.5, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
        ],
      },
    ])

    expect(summary[0]).toEqual({ lampIndex: 1, settledAngle: null, bandMin: null, bandMax: null, flips: 0 })
  })
})

describe('stableTransitionEvents', () => {
  it('suppresses one-frame tracking blips while keeping the sustained crossing', () => {
    const noisyTrackingResult = {
      original_filename: 'sample.mp4',
      transition_method: 'tracking',
      angle_track: [
        { frame_index: 26, elevation_angle_deg: 2.32, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 27, elevation_angle_deg: 2.37, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 28, elevation_angle_deg: 2.41, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 29, elevation_angle_deg: 2.46, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 30, elevation_angle_deg: 2.52, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 31, elevation_angle_deg: 2.57, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 32, elevation_angle_deg: 2.61, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 33, elevation_angle_deg: 2.66, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 47, elevation_angle_deg: 3.34, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 48, elevation_angle_deg: 3.39, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 49, elevation_angle_deg: 3.45, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 50, elevation_angle_deg: 3.48, lamps: [{ index: 1, state: 'white' }] },
      ],
      transitions: [
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 28, elevation_angle_deg: 2.41 },
        { lamp_index: 1, from_state: 'white', to_state: 'red', frame_index: 29, elevation_angle_deg: 2.46 },
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 32, elevation_angle_deg: 2.61 },
        { lamp_index: 1, from_state: 'white', to_state: 'red', frame_index: 48, elevation_angle_deg: 3.39 },
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 49, elevation_angle_deg: 3.45 },
      ],
    }
    const events = stableTransitionEvents([noisyTrackingResult])

    expect(events).toEqual([
      {
        lamp_index: 1,
        from_state: 'red',
        to_state: 'white',
        frame_index: 32,
        elevation_angle_deg: 2.61,
        method: 'tracking',
      },
    ])
    expect(transitionAngleSummary([noisyTrackingResult])[0].settledAngle).toBeCloseTo(2.61, 5)
  })

  it('keeps valid model transition runs from the backend', () => {
    const raw = [{ lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 12, method: 'model' }]

    expect(stableTransitionEvents([{ transition_method: 'model', angle_track: [], transitions: raw }])).toEqual(raw)
  })

  it('drops model transition runs that do not change colour', () => {
    const raw = [
      { lamp_index: 1, from_state: 'red', to_state: 'red', frame_index: 12, method: 'model' },
      { lamp_index: 2, from_state: 'white', to_state: 'red', frame_index: 20, method: 'model' },
    ]

    expect(stableTransitionEvents([{ transition_method: 'model', angle_track: [], transitions: raw }])).toEqual([
      raw[1],
    ])
  })

  it('uses full-resolution backend tracking transitions when angle_track is downsampled', () => {
    const result = {
      transition_method: 'tracking',
      frame_count: 600,
      angle_track: [
        { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 599, elevation_angle_deg: 4.0, lamps: [{ index: 1, state: 'white' }] },
      ],
      transitions: [
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 251, elevation_angle_deg: 2.76 },
      ],
    }

    expect(stableTransitionEvents([result])).toEqual([
      {
        lamp_index: 1,
        from_state: 'red',
        to_state: 'white',
        frame_index: 251,
        elevation_angle_deg: 2.76,
        method: 'tracking',
      },
    ])
  })

  it('treats an empty backend transitions array as authoritative', () => {
    const result = {
      transition_method: 'tracking',
      transitions: [],
      angle_track: [
        { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 1, elevation_angle_deg: 2.1, lamps: [{ index: 1, state: 'white' }] },
      ],
    }

    expect(stableTransitionEvents([result])).toEqual([])
  })
})

describe('transitionFlickerStatus', () => {
  it('classifies no crossing, clean crossing, and repeated-flip review cases', () => {
    expect(transitionFlickerStatus(0)).toBe('no_crossing')
    expect(transitionFlickerStatus(1)).toBe('clean_crossing')
    expect(transitionFlickerStatus(2)).toBe('review_flicker')
  })
})

describe('transitionCsv', () => {
  it('exports only real transition events and flags repeated flips by lamp', () => {
    const csv = transitionCsv(
      [
        {
          log_id: 'log-1',
          runway_id: 'papi_24',
          original_filename: 'clip, one.mp4',
          transition_method: 'tracking',
          transitions: [
            { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 2, elevation_angle_deg: 2.7, method: 'tracking' },
            { lamp_index: 1, from_state: 'white', to_state: 'red', frame_index: 6, elevation_angle_deg: 2.9, method: 'tracking' },
            { lamp_index: 5, from_state: 'red', to_state: 'white', frame_index: 4, elevation_angle_deg: 3.1 },
          ],
        },
      ],
      { mode: 'history' },
    )

    const rows = csv.split('\r\n')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toContain('flicker_status')
    expect(rows[1]).toContain('"clip, one.mp4"')
    expect(rows[1]).toContain('review_flicker')
    expect(rows[2]).toContain('review_flicker')
    expect(csv).not.toContain(',5,')
  })
})

describe('summarizeSession', () => {
  it('counts crossed lamps from stabilized backend transitions, not discarded angle_track flips', () => {
    const summary = summarizeSession([
      {
        transition_method: 'tracking',
        transitions: [],
        frame_count: 4,
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
          { frame_index: 3, elevation_angle_deg: 3.5, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
        ],
      },
    ])

    expect(summary.lampsDetected).toBe(1)
    expect(summary.lampsCrossed).toBe(0)
  })

  it('keeps the legacy angle_track fallback for results without backend transition authority', () => {
    const summary = summarizeSession([
      {
        frame_count: 4,
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
          { frame_index: 3, elevation_angle_deg: 3.5, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
        ],
      },
    ])

    expect(summary.lampsCrossed).toBe(1)
  })
})

describe('stateBandSeries', () => {
  it('returns no blocks when no result carries a track', () => {
    expect(stateBandSeries([])).toEqual([])
    expect(stateBandSeries([{ lamps: [{ index: 1, state: 'red' }] }])).toEqual([])
  })

  it('codes per-frame lamp states per light, absent slots as unknown (0)', () => {
    const blocks = stateBandSeries([
      {
        original_filename: 'clip.mp4',
        angle_track: [
          {
            frame_index: 0,
            elevation_angle_deg: 2.0,
            lamps: [
              { index: 1, state: 'red', confidence: 0.8 },
              { index: 2, state: 'white', confidence: 0.7 },
            ],
          },
          {
            frame_index: 1,
            elevation_angle_deg: null, // angle missing -> kept as null, frame still coded
            lamps: [{ index: 1, state: 'transition', confidence: 0.6 }],
          },
        ],
      },
    ])
    expect(blocks).toHaveLength(1)
    expect(blocks[0].label).toBe('clip.mp4')
    expect(blocks[0].frames).toEqual([0, 1])
    expect(blocks[0].angles).toEqual([2.0, null])
    // Row order = Light 1..4; codes: unknown 0, obscured 1, red 2, transition 3, white 4.
    expect(blocks[0].z[0]).toEqual([2, 3]) // light 1: red then transition
    expect(blocks[0].z[1]).toEqual([4, 0]) // light 2: white then absent -> unknown
    expect(blocks[0].z[2]).toEqual([0, 0]) // light 3 never seen
  })

  it('skips samples without a finite frame index', () => {
    const blocks = stateBandSeries([
      {
        angle_track: [
          { frame_index: null, elevation_angle_deg: 2.0, lamps: [] },
          { frame_index: 1, elevation_angle_deg: 2.1, lamps: [] },
        ],
      },
    ])
    expect(blocks[0].frames).toEqual([1])
  })

  it('uses full-resolution per_frame lamp states for state bands when present', () => {
    const blocks = stateBandSeries([
      {
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red' }] },
          { frame_index: 2, elevation_angle_deg: 2.2, lamps: [{ index: 1, state: 'white' }] },
        ],
        per_frame: [
          { frame_index: 0, state: 'unknown', confidence: 0.5, lamps: [{ index: 1, state: 'red' }] },
          { frame_index: 1, state: 'unknown', confidence: 0.5, lamps: [{ index: 1, state: 'red' }] },
          { frame_index: 2, state: 'unknown', confidence: 0.5, lamps: [{ index: 1, state: 'white' }] },
        ],
      },
    ])

    expect(blocks[0].frames).toEqual([0, 1, 2])
    expect(blocks[0].angles).toEqual([2.0, null, 2.2])
    expect(blocks[0].z[0]).toEqual([2, 2, 4])
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

  it('counts PER FRAME when a result carries an angle_track (absent slot = unknown)', () => {
    const series = perLightStateSeries([
      {
        // The aggregate says "red" — but the frames tell the real story and must win.
        lamps: [{ index: 1, state: 'red', confidence: 0.8 }],
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 1, elevation_angle_deg: 2.5, lamps: [{ index: 1, state: 'red', confidence: 0.8 }] },
          { frame_index: 2, elevation_angle_deg: 3.0, lamps: [{ index: 1, state: 'white', confidence: 0.8 }] },
          { frame_index: 3, elevation_angle_deg: 3.5, lamps: [] },
        ],
      },
    ])
    expect(series[0]).toEqual({ white: 1, red: 2, transition: 0, obscured: 0, unknown: 1 })
    // Lights never present in any frame are all-unknown, not silently zero.
    expect(series[1].unknown).toBe(4)
  })

  it('prefers full-resolution per_frame lamp states over downsampled angle_track states', () => {
    const series = perLightStateSeries([
      {
        frame_count: 3,
        per_frame: [
          { frame_index: 0, state: 'unknown', confidence: 0.5, lamps: [{ index: 1, state: 'red' }] },
          { frame_index: 1, state: 'unknown', confidence: 0.5, lamps: [{ index: 1, state: 'red' }] },
          { frame_index: 2, state: 'unknown', confidence: 0.5, lamps: [{ index: 1, state: 'white' }] },
        ],
        angle_track: [
          { frame_index: 0, elevation_angle_deg: 2.0, lamps: [{ index: 1, state: 'red' }] },
          { frame_index: 2, elevation_angle_deg: 2.2, lamps: [{ index: 1, state: 'white' }] },
        ],
      },
    ])

    expect(series[0]).toEqual({ white: 1, red: 2, transition: 0, obscured: 0, unknown: 0 })
  })

  it('keeps aggregate counting for results without a track', () => {
    const series = perLightStateSeries([
      { lamps: [{ index: 1, state: 'red', confidence: 0.8 }], angle_track: [] },
    ])
    expect(series[0].red).toBe(1)
    expect(series[0].unknown).toBe(0)
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
