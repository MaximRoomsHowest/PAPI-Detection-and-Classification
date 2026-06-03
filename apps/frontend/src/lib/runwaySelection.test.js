import { describe, expect, it } from 'vitest'
import { resolveRunwayId } from './runwaySelection.js'

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
    expect(resolveRunwayId('anything', [])).toBe('papi_24')
    expect(resolveRunwayId(null, undefined)).toBe('papi_24')
  })

  it('treats a null/empty candidate as a miss and resolves to a safe default', () => {
    expect(resolveRunwayId(null, runways)).toBe('papi_24')
    expect(resolveRunwayId('', runways)).toBe('papi_24')
  })
})
