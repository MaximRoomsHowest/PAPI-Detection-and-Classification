import { describe, expect, it } from 'vitest'
import { lampPattern, scenarioFromBackendResult, scenarioFromVideoFrameResult } from './papi.js'

// Mirrors the backend AnalysisPayload shape (see baseline POST /api/analyze-frame:
// far_too_low, four red lamps). Override per-test to exercise a branch.
function makeResult(overrides = {}) {
  return {
    media_type: 'image',
    global_state: 'far_too_low',
    confidence: 0.61,
    processing_ms: 1234,
    log_id: 'abcdef1234567890',
    artifact_url: '/media/x_annotated.jpg',
    lamps: [
      { index: 1, state: 'red', confidence: 0.64, bbox: { x1: 1, y1: 2, x2: 3, y2: 4 } },
      { index: 2, state: 'red', confidence: 0.63, bbox: null },
      { index: 3, state: 'white', confidence: 0.74, bbox: null },
      { index: 4, state: 'unknown', confidence: 0, bbox: null },
    ],
    angle: {
      angle_available: true,
      elevation_angle_deg: -2.5,
      angle_source: 'file_metadata',
      angle_note: 'ok',
    },
    transitions: [],
    ...overrides,
  }
}

const context = { frameLabel: 'Frame 1', totalFrames: 1 }

describe('lampPattern', () => {
  it('joins per-lamp states and maps any unrecognised state to unknown', () => {
    expect(
      lampPattern([{ state: 'white' }, { state: 'red' }, { state: 'transition' }, { state: 'weird' }]),
    ).toBe('white + red + transition + unknown')
  })
})

describe('scenarioFromBackendResult', () => {
  it('maps each global_state to the matching state-catalog id and label', () => {
    expect(scenarioFromBackendResult(makeResult({ global_state: 'far_too_high' }), context).stateId).toBe('far-high')
    const correct = scenarioFromBackendResult(makeResult({ global_state: 'correct_glidepath' }), context)
    expect(correct.stateId).toBe('correct')
    expect(correct.summary).toContain('correct glidepath')
    expect(scenarioFromBackendResult(makeResult({ global_state: 'transition' }), context).stateId).toBe('transition')
  })

  it('falls back to unknown for an unrecognised global_state', () => {
    expect(scenarioFromBackendResult(makeResult({ global_state: 'nonsense' }), context).stateId).toBe('unknown')
  })

  it('maps lamps: unknown -> occluded, confidence -> percent, bbox preserved', () => {
    const lamps = scenarioFromBackendResult(makeResult(), context).lamps
    expect(lamps).toHaveLength(4)
    expect(lamps[0]).toMatchObject({ id: 1, status: 'red', confidence: 64, bbox: { x1: 1, y1: 2, x2: 3, y2: 4 } })
    expect(lamps[3].status).toBe('occluded')
    expect(lamps[3].confidence).toBe(0)
  })

  it('formats an available angle and the box-confidence percentage', () => {
    const s = scenarioFromBackendResult(makeResult(), context)
    expect(s.condition).toBe('-2.500 deg')
    expect(s.angleSummary).toMatchObject({ available: true, value: '-2.500', source: 'file_metadata' })
    expect(s.metrics.boxConfidence).toBe(61)
  })

  it('defaults the new angle fields when the payload omits them (back-compat)', () => {
    const s = scenarioFromBackendResult(makeResult(), context)
    expect(s.angleSummary).toMatchObject({
      plausible: true,
      plausibilityNote: null,
      nearestLampDistanceM: null,
      uncertainty: null,
    })
  })

  it('surfaces plausibility, nearest-lamp distance and RTK uncertainty from the angle', () => {
    const s = scenarioFromBackendResult(
      makeResult({
        angle: {
          angle_available: true,
          elevation_angle_deg: -2.5,
          angle_source: 'request_metadata',
          angle_note: 'ok',
          plausible: false,
          plausibility_note: 'too far from runway',
          nearest_lamp_distance_m: 530000,
          elevation_angle_uncertainty_deg: 0.04,
        },
      }),
      context,
    )
    expect(s.angleSummary).toMatchObject({
      available: true,
      source: 'request_metadata',
      plausible: false,
      plausibilityNote: 'too far from runway',
      nearestLampDistanceM: 530000,
      uncertainty: 0.04,
    })
  })

  it('treats angle_available with a null elevation as unavailable (guards toFixed)', () => {
    const s = scenarioFromBackendResult(
      makeResult({ angle: { angle_available: true, elevation_angle_deg: null } }),
      context,
    )
    expect(s.condition).toBe('Angle unavailable')
    expect(s.angleSummary.available).toBe(false)
  })

  it('treats a missing angle object as unavailable without throwing', () => {
    const s = scenarioFromBackendResult(makeResult({ angle: undefined }), context)
    expect(s.angleSummary.available).toBe(false)
    expect(s.condition).toBe('Angle unavailable')
  })

  it('exposes the backend angle_source as sourceId on available summaries', () => {
    const s = scenarioFromBackendResult(makeResult(), context)
    expect(s.angleSummary.sourceId).toBe('file_metadata')
  })

  it('keeps sourceId when telemetry was present but the angle could not be computed (FE-17)', () => {
    const s = scenarioFromBackendResult(
      makeResult({
        angle: {
          angle_available: true,
          elevation_angle_deg: null,
          angle_source: 'request_metadata',
          angle_note: 'angle solve failed',
        },
      }),
      context,
    )
    expect(s.angleSummary.available).toBe(false)
    expect(s.angleSummary.sourceId).toBe('request_metadata')
  })

  it('leaves sourceId null when no telemetry was resolved', () => {
    expect(
      scenarioFromBackendResult(
        makeResult({ angle: { angle_available: false, angle_note: 'no metadata' } }),
        context,
      ).angleSummary.sourceId,
    ).toBeNull()
    expect(
      scenarioFromBackendResult(makeResult({ angle: undefined }), context).angleSummary.sourceId,
    ).toBeNull()
  })

  it('clamps a negative processing time to zero latency', () => {
    expect(scenarioFromBackendResult(makeResult({ processing_ms: -5 }), context).metrics.latency).toBe(0)
  })

  it('badges with the short log id when present and "live" otherwise', () => {
    expect(scenarioFromBackendResult(makeResult({ log_id: 'abcdef1234567890' }), context).badge).toBe('log abcdef12')
    expect(scenarioFromBackendResult(makeResult({ log_id: null }), context).badge).toBe('live')
  })

  it('labels multi-frame context as "label of N"', () => {
    expect(scenarioFromBackendResult(makeResult(), { frameLabel: 'Frame 2', totalFrames: 5 }).frame).toBe('Frame 2 of 5')
  })

  it('uses a resolved artifact URL when the caller provides one', () => {
    const s = scenarioFromBackendResult(makeResult(), { ...context, artifactUrl: 'blob:http://example.test/a' })
    expect(s.artifactUrl).toBe('blob:http://example.test/a')
  })

  it('defaults transitions to an empty array and keeps the raw payload', () => {
    const result = makeResult({ transitions: undefined })
    const s = scenarioFromBackendResult(result, context)
    expect(s.transitions).toEqual([])
    expect(s.rawResult).toBe(result)
    expect(s.artifactType).toBe('image')
  })

  it('preserves per-frame backend series for video and folder-sequence charts', () => {
    const perFrame = [
      { frame_index: 0, global_state: 'transition', confidence: 0.8 },
      { frame_index: 1, global_state: 'correct_glidepath', confidence: 0.9 },
    ]

    const s = scenarioFromBackendResult(makeResult({ media_type: 'video', per_frame: perFrame }), context)

    expect(s.perFrame).toBe(perFrame)
    expect(s.artifactType).toBe('video')
  })
})

describe('scenarioFromVideoFrameResult', () => {
  it('uses the selected frame state, confidence, angle, and lamp states', () => {
    const result = makeResult({
      media_type: 'video',
      frame_count: 3,
      global_state: 'far_too_low',
      confidence: 0.5,
      per_frame: [
        { frame_index: 0, state: 'far_too_low', confidence: 0.4 },
        { frame_index: 1, state: 'correct_glidepath', confidence: 0.8 },
        { frame_index: 2, state: 'far_too_high', confidence: 0.7 },
      ],
      angle_track: [
        {
          frame_index: 1,
          elevation_angle_deg: 3.125,
          lamps: [
            { index: 1, state: 'red', confidence: 0.9 },
            { index: 2, state: 'red', confidence: 0.8 },
            { index: 3, state: 'white', confidence: 0.7 },
            { index: 4, state: 'white', confidence: 0.6 },
          ],
        },
      ],
    })
    const base = scenarioFromBackendResult(result, context)
    const frame = scenarioFromVideoFrameResult(result, base, 1)

    expect(frame.stateId).toBe('correct')
    expect(frame.metrics.boxConfidence).toBe(80)
    expect(frame.angleSummary).toMatchObject({ available: true, value: '3.125' })
    expect(frame.summary).toContain('red + red + white + white')
    expect(frame.lamps.map((lamp) => lamp.status)).toEqual(['red', 'red', 'white', 'white'])
  })

  it('fills a missing per-frame lamp as occluded instead of reusing the aggregate lamp', () => {
    const result = makeResult({
      media_type: 'video',
      frame_count: 1,
      per_frame: [{ frame_index: 0, state: 'unknown', confidence: 0.3 }],
      angle_track: [
        {
          frame_index: 0,
          elevation_angle_deg: 2.8,
          lamps: [
            { index: 1, state: 'red', confidence: 0.9 },
            { index: 2, state: 'red', confidence: 0.8 },
            { index: 3, state: 'white', confidence: 0.7 },
          ],
        },
      ],
    })
    const frame = scenarioFromVideoFrameResult(result, scenarioFromBackendResult(result, context), 0)

    expect(frame.lamps).toHaveLength(4)
    expect(frame.lamps[3]).toMatchObject({ id: 4, status: 'occluded', confidence: 0 })
  })
})
