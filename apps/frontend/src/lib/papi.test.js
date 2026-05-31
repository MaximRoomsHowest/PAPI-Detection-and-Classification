import { describe, expect, it } from 'vitest'
import { lampPattern, scenarioFromBackendResult } from './papi.js'

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

  it('defaults transitions to an empty array and keeps the raw payload', () => {
    const result = makeResult({ transitions: undefined })
    const s = scenarioFromBackendResult(result, context)
    expect(s.transitions).toEqual([])
    expect(s.rawResult).toBe(result)
    expect(s.artifactType).toBe('image')
  })
})
