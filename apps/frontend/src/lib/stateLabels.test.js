import { describe, expect, it } from 'vitest'
import { translations } from '../i18n/translations.js'
import { globalStateLabel, lampStateLabel } from './stateLabels.js'

describe('globalStateLabel', () => {
  it.each([
    ['en', 'correct_glidepath', 'Correct glidepath'],
    ['de', 'correct_glidepath', 'Korrekter Gleitweg'],
    ['nl', 'correct_glidepath', 'Correct glijpad'],
    ['fr', 'correct_glidepath', 'Plan correct'],
  ])('localizes a mapped backend state (%s)', (locale, raw, expected) => {
    expect(globalStateLabel(raw, translations[locale])).toBe(expected)
  })

  it('localizes every backend GlobalState the API can return', () => {
    const backendStates = [
      'far_too_high',
      'too_high',
      'correct_glidepath',
      'too_low',
      'far_too_low',
      'transition',
      'unknown',
    ]
    for (const locale of ['en', 'de', 'nl', 'fr']) {
      for (const raw of backendStates) {
        const label = globalStateLabel(raw, translations[locale])
        // Localized labels never leak the raw snake_case enum.
        expect(label).not.toContain('_')
        expect(label.length).toBeGreaterThan(0)
      }
    }
  })

  it('prettifies an unmapped raw value instead of dropping it', () => {
    expect(globalStateLabel('partially_visible', translations.en)).toBe('partially visible')
  })

  it('returns an empty string for a missing value', () => {
    expect(globalStateLabel(null, translations.en)).toBe('')
  })
})

describe('lampStateLabel', () => {
  it('localizes lamp colours via the status map', () => {
    expect(lampStateLabel('obscured', translations.de)).toBe('Verdeckt')
    expect(lampStateLabel('white', translations.fr)).toBe(translations.fr.status.white)
  })

  it('falls back to the raw value when unmapped', () => {
    expect(lampStateLabel('flickering', translations.en)).toBe('flickering')
  })
})
