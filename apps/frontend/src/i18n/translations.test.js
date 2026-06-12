import { describe, expect, it } from 'vitest'
import { translations } from './translations'

// Every locale must expose exactly the same key tree: a key added to en but not
// de/nl/fr surfaces as raw-undefined text only on the untranslated locales, which
// no English-language test or reviewer ever sees. Parity was previously checked
// ad hoc; this pins it permanently (audit follow-up to the i18n fixes).
function keyPaths(node, prefix = '') {
  return Object.entries(node).flatMap(([key, value]) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? keyPaths(value, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  )
}

describe('translations', () => {
  const locales = Object.keys(translations)

  it('covers the four shipped locales', () => {
    expect(locales.sort()).toEqual(['de', 'en', 'fr', 'nl'])
  })

  it('keeps exact key parity across all locales', () => {
    const reference = keyPaths(translations.en).sort()
    for (const locale of locales) {
      expect(keyPaths(translations[locale]).sort(), `locale ${locale}`).toEqual(reference)
    }
  })

  it('keeps {placeholder} tokens consistent across locales', () => {
    const placeholders = (text) => (typeof text === 'string' ? (text.match(/\{[a-zA-Z]+\}/g) ?? []).sort() : [])
    const flatten = (node, prefix = '') =>
      Object.fromEntries(
        Object.entries(node).flatMap(([key, value]) =>
          value && typeof value === 'object' && !Array.isArray(value)
            ? Object.entries(flatten(value, `${prefix}${key}.`))
            : [[`${prefix}${key}`, placeholders(value)]],
        ),
      )
    const reference = flatten(translations.en)
    for (const locale of locales) {
      const flat = flatten(translations[locale])
      for (const [path, tokens] of Object.entries(reference)) {
        expect(flat[path], `${locale}:${path}`).toEqual(tokens)
      }
    }
  })
})
