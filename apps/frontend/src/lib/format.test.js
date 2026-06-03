/**
 * Tests for the small display formatters (timestamps, durations, angles).
 *
 * Behaviour pinned against the real implementation — note the deliberately
 * subtle coercion edges:
 *   - formatAngle uses `Number.isFinite(Number(value))`. Because `Number(null)`
 *     and `Number('')` are BOTH 0 (finite), those render as "0.000°", whereas
 *     `undefined`/'abc'/NaN coerce to NaN and yield the fallback. This is real,
 *     intentional behaviour (the caller passes numeric angles), so we pin it.
 *   - formatDurationMs returns a { value, suffix } pair (InlineMetric props),
 *     switches to seconds at >= 1000 ms, drops the decimal at >= 10000 ms, and
 *     floors negatives/non-numbers to { value: 0, suffix: ' ms' }.
 *   - formatTimestamp returns the em-dash placeholder for falsy input and
 *     echoes the original string back when it isn't a parseable date.
 */

import { describe, it, expect } from 'vitest'

import { formatAngle, formatDurationMs, formatTimestamp } from './format.js'

describe('formatAngle', () => {
  it('formats a finite number to 3 decimals with a degree sign', () => {
    expect(formatAngle(3)).toBe('3.000°')
    expect(formatAngle(2.71828)).toBe('2.718°')
    expect(formatAngle(-1.5)).toBe('-1.500°')
  })

  it('accepts numeric strings (coerced via Number)', () => {
    expect(formatAngle('2.5')).toBe('2.500°')
  })

  it('treats null and empty string as 0 (Number coerces them to 0, which is finite)', () => {
    expect(formatAngle(null)).toBe('0.000°')
    expect(formatAngle('')).toBe('0.000°')
  })

  it('returns the fallback for undefined, NaN, and non-numeric strings', () => {
    expect(formatAngle(undefined)).toBe('—')
    expect(formatAngle(NaN)).toBe('—')
    expect(formatAngle('abc')).toBe('—')
  })

  it('honours a custom fallback', () => {
    expect(formatAngle(undefined, 'n/a')).toBe('n/a')
  })
})

describe('formatDurationMs', () => {
  it('renders sub-second values as rounded milliseconds', () => {
    expect(formatDurationMs(450)).toEqual({ value: 450, suffix: ' ms' })
    expect(formatDurationMs(0)).toEqual({ value: 0, suffix: ' ms' })
    expect(formatDurationMs(12.6)).toEqual({ value: 13, suffix: ' ms' })
  })

  it('renders 1s..<10s with one decimal in seconds', () => {
    expect(formatDurationMs(1000)).toEqual({ value: '1.0', suffix: ' s' })
    expect(formatDurationMs(1500)).toEqual({ value: '1.5', suffix: ' s' })
    expect(formatDurationMs(9999)).toEqual({ value: '10.0', suffix: ' s' })
  })

  it('drops the decimal at >= 10000 ms', () => {
    expect(formatDurationMs(10000)).toEqual({ value: '10', suffix: ' s' })
    expect(formatDurationMs(45000)).toEqual({ value: '45', suffix: ' s' })
  })

  it('floors negatives and non-numbers to a zero-ms pair', () => {
    expect(formatDurationMs(-5)).toEqual({ value: 0, suffix: ' ms' })
    expect(formatDurationMs(NaN)).toEqual({ value: 0, suffix: ' ms' })
    expect(formatDurationMs(undefined)).toEqual({ value: 0, suffix: ' ms' })
    expect(formatDurationMs('not a number')).toEqual({ value: 0, suffix: ' ms' })
  })

  it('coerces numeric strings before formatting', () => {
    expect(formatDurationMs('2000')).toEqual({ value: '2.0', suffix: ' s' })
  })
})

describe('formatTimestamp', () => {
  it('returns the em-dash placeholder for falsy input', () => {
    expect(formatTimestamp(undefined)).toBe('—')
    expect(formatTimestamp(null)).toBe('—')
    expect(formatTimestamp('')).toBe('—')
    expect(formatTimestamp(0)).toBe('—')
  })

  it('echoes the original value back when it is not a parseable date', () => {
    expect(formatTimestamp('not-a-date')).toBe('not-a-date')
  })

  it('returns a non-empty formatted string for a valid ISO timestamp', () => {
    // The exact text is locale/timezone dependent, so we only assert that a
    // valid date produces a real string that is neither the placeholder nor
    // the raw input echo.
    const iso = '2026-06-02T12:34:00Z'
    const out = formatTimestamp(iso)
    expect(typeof out).toBe('string')
    expect(out.length).toBeGreaterThan(0)
    expect(out).not.toBe('—')
    expect(out).not.toBe(iso)
  })

  it('accepts an epoch-millis number for a valid date', () => {
    const out = formatTimestamp(Date.UTC(2026, 5, 2, 12, 0, 0))
    expect(typeof out).toBe('string')
    expect(out).not.toBe('—')
  })
})
