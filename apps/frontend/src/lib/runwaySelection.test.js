import { describe, expect, it } from 'vitest'
import {
  DEFAULT_RUNWAY_ID,
  resolveRunwayId,
  runwayDisplayName,
  sessionRunwaySummary,
} from './runwaySelection.js'

const runways = [
  { id: 'papi_06', label: 'PAPI 06' },
  { id: 'papi_24', label: 'PAPI 24' },
  { id: 'custom_x', label: 'Custom X' },
]

describe('resolveRunwayId', () => {
  it('keeps the candidate when it still exists in the list', () => {
    expect(resolveRunwayId('custom_x', runways)).toBe('custom_x')
  })

  it('falls back to papi_24 when the candidate is missing but papi_24 exists', () => {
    expect(resolveRunwayId('deleted_id', runways)).toBe('papi_24')
  })

  it('falls back to the first runway when neither the candidate nor papi_24 exist', () => {
    const list = [
      { id: 'papi_06', label: 'PAPI 06' },
      { id: 'custom_x', label: 'Custom X' },
    ]
    expect(resolveRunwayId('deleted_id', list)).toBe('papi_06')
  })

  it('returns papi_24 for an empty or missing list', () => {
    expect(resolveRunwayId('anything', [])).toBe(DEFAULT_RUNWAY_ID)
    expect(resolveRunwayId(null, undefined)).toBe(DEFAULT_RUNWAY_ID)
  })

  it('treats a null/empty candidate as a miss and resolves to a safe default', () => {
    expect(resolveRunwayId(null, runways)).toBe('papi_24')
    expect(resolveRunwayId('', runways)).toBe('papi_24')
  })
})

describe('runwayDisplayName', () => {
  it('returns the current runway label for known ids', () => {
    expect(runwayDisplayName('custom_x', runways)).toBe('Custom X')
  })

  it('falls back to the raw id for deleted or unknown custom runways', () => {
    expect(runwayDisplayName('deleted_custom', runways)).toBe('deleted_custom')
  })

  it('uses the default runway id when no id is supplied', () => {
    expect(runwayDisplayName(null, [])).toBe(DEFAULT_RUNWAY_ID)
  })
})

describe('sessionRunwaySummary', () => {
  it('returns none when the session has no runway ids', () => {
    expect(sessionRunwaySummary([{ runway_id: null }, {}], runways)).toEqual({
      kind: 'none',
      ids: [],
      label: null,
    })
  })

  it('summarizes a single-runway session with its display label', () => {
    expect(sessionRunwaySummary([{ runway_id: 'papi_24' }, { runway_id: 'papi_24' }], runways)).toEqual({
      kind: 'single',
      ids: ['papi_24'],
      label: 'PAPI 24',
    })
  })

  it('summarizes mixed-runway sessions in first-seen order', () => {
    expect(sessionRunwaySummary([{ runway_id: 'custom_x' }, { runway_id: 'papi_06' }], runways)).toEqual({
      kind: 'mixed',
      ids: ['custom_x', 'papi_06'],
      label: 'Custom X, PAPI 06',
    })
  })

  it('keeps raw ids in mixed summaries when a custom runway was deleted', () => {
    expect(sessionRunwaySummary([{ runway_id: 'custom_deleted' }, { runway_id: 'papi_24' }], runways)).toEqual({
      kind: 'mixed',
      ids: ['custom_deleted', 'papi_24'],
      label: 'custom_deleted, PAPI 24',
    })
  })
})
