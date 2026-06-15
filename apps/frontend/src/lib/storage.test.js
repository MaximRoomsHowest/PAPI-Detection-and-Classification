/**
 * Tests for the localStorage persistence wrappers (theme + language choice).
 *
 * NOTE on scope: the real module does NOT JSON-parse stored values — it stores
 * plain strings and validates reads against an allow-list. The "parse failure"
 * resilience here is the try/catch around localStorage access itself (Safari
 * private mode throws on get/set; SSR has no `window`). We pin:
 *   - safeLocalStorageSet writes through and swallows a throwing setItem.
 *   - readStoredChoice returns the stored value only when it's in the allow-list,
 *     else the fallback; and returns the fallback when getItem throws.
 *   - initialTheme / initialLanguage precedence (stored -> system/navigator ->
 *     default).
 *
 * jsdom provides a real `window.localStorage`; we clear it per test and, for the
 * throw paths, temporarily swap in a storage stub whose methods throw.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

import {
  STORAGE_KEYS,
  CONSENT_KEY,
  safeLocalStorageSet,
  setPreference,
  getConsentDecision,
  setConsentDecision,
  resetConsentDecision,
  readStoredChoice,
  readStoredString,
  initialTheme,
  initialLanguage,
  initialRunwayId,
} from './storage.js'

// jsdom's window.localStorage is a Storage instance whose methods live on an
// exotic prototype; spying the instance method doesn't reliably intercept the
// call the module makes. To exercise the throw paths we swap the whole object
// for a stub, then restore. realLocalStorage is captured once up front.
const realLocalStorage = window.localStorage

function withLocalStorage(stub, fn) {
  Object.defineProperty(window, 'localStorage', { configurable: true, value: stub })
  try {
    return fn()
  } finally {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: realLocalStorage,
    })
  }
}

beforeEach(() => {
  window.localStorage.clear()
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({ matches: false }),
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('STORAGE_KEYS', () => {
  it('exposes the namespaced keys the app reads/writes', () => {
    expect(STORAGE_KEYS.theme).toBe('papi.theme.v2')
    expect(STORAGE_KEYS.language).toBe('papi.language')
    expect(STORAGE_KEYS.runway).toBe('papi.runway')
  })
})

describe('safeLocalStorageSet', () => {
  it('writes the value through to localStorage', () => {
    safeLocalStorageSet('papi.test', 'hello')
    expect(window.localStorage.getItem('papi.test')).toBe('hello')
  })

  it('swallows errors when setItem throws (e.g. Safari private mode)', () => {
    let called = false
    const throwingStorage = {
      setItem: () => {
        called = true
        throw new DOMException('QuotaExceededError')
      },
    }
    withLocalStorage(throwingStorage, () => {
      // Must not throw despite the underlying failure.
      expect(() => safeLocalStorageSet('papi.test', 'x')).not.toThrow()
    })
    expect(called).toBe(true)
  })
})

describe('storage consent', () => {
  it('returns null when no decision has been recorded', () => {
    expect(getConsentDecision()).toBeNull()
  })

  it('persists a versioned record that getConsentDecision reads back', () => {
    setConsentDecision('accepted')
    expect(getConsentDecision()).toBe('accepted')
    const raw = JSON.parse(window.localStorage.getItem(CONSENT_KEY))
    expect(raw.v).toBe(1)
    expect(raw.decision).toBe('accepted')
  })

  it('ignores an unknown decision and a wrong-version record', () => {
    setConsentDecision('bogus')
    expect(window.localStorage.getItem(CONSENT_KEY)).toBeNull()
    window.localStorage.setItem(CONSENT_KEY, JSON.stringify({ v: 999, decision: 'accepted' }))
    expect(getConsentDecision()).toBeNull()
  })

  it('declining clears any previously-stored preferences', () => {
    window.localStorage.setItem(STORAGE_KEYS.theme, 'light')
    window.localStorage.setItem(STORAGE_KEYS.runway, 'custom_x')
    setConsentDecision('declined')
    expect(getConsentDecision()).toBe('declined')
    expect(window.localStorage.getItem(STORAGE_KEYS.theme)).toBeNull()
    expect(window.localStorage.getItem(STORAGE_KEYS.runway)).toBeNull()
  })

  it('resetConsentDecision forgets the choice so the banner shows again', () => {
    setConsentDecision('accepted')
    resetConsentDecision()
    expect(getConsentDecision()).toBeNull()
  })
})

describe('setPreference (consent-gated)', () => {
  it('does not write while undecided', () => {
    expect(setPreference(STORAGE_KEYS.theme, 'light')).toBe(false)
    expect(window.localStorage.getItem(STORAGE_KEYS.theme)).toBeNull()
  })

  it('does not write when declined', () => {
    setConsentDecision('declined')
    expect(setPreference(STORAGE_KEYS.theme, 'light')).toBe(false)
    expect(window.localStorage.getItem(STORAGE_KEYS.theme)).toBeNull()
  })

  it('writes through once accepted', () => {
    setConsentDecision('accepted')
    expect(setPreference(STORAGE_KEYS.theme, 'light')).toBe(true)
    expect(window.localStorage.getItem(STORAGE_KEYS.theme)).toBe('light')
  })
})

describe('readStoredChoice', () => {
  it('returns the stored value when it is present and allow-listed', () => {
    window.localStorage.setItem('k', 'dark')
    expect(readStoredChoice('k', ['light', 'dark'], 'light')).toBe('dark')
  })

  it('returns the fallback when the stored value is not in the allow-list', () => {
    window.localStorage.setItem('k', 'chartreuse')
    expect(readStoredChoice('k', ['light', 'dark'], 'light')).toBe('light')
  })

  it('returns the fallback when nothing is stored', () => {
    expect(readStoredChoice('missing', ['light', 'dark'], 'light')).toBe('light')
  })

  it('returns the fallback when getItem throws (resilience path)', () => {
    const throwingStorage = {
      getItem: () => {
        throw new DOMException('SecurityError')
      },
    }
    const result = withLocalStorage(throwingStorage, () =>
      readStoredChoice('k', ['light', 'dark'], 'light'),
    )
    expect(result).toBe('light')
  })
})

describe('initialTheme', () => {
  it('returns a persisted, valid theme over the system preference', () => {
    window.localStorage.setItem(STORAGE_KEYS.theme, 'dark')
    expect(initialTheme()).toBe('dark')
  })

  it('falls back to dark when nothing valid is stored, even if the system prefers dark', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true })
    expect(initialTheme()).toBe('dark')
  })

  it('falls back to dark when nothing is stored and the system prefers light', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: false })
    expect(initialTheme()).toBe('dark')
  })
})

describe('readStoredString', () => {
  it('returns the stored string as-is (no allow-list — runway ids are dynamic)', () => {
    window.localStorage.setItem('k', 'custom_my_runway')
    expect(readStoredString('k', 'papi_24')).toBe('custom_my_runway')
  })

  it('returns the fallback when nothing is stored', () => {
    expect(readStoredString('missing', 'papi_24')).toBe('papi_24')
  })

  it('returns the fallback when getItem throws (resilience path)', () => {
    const throwingStorage = {
      getItem: () => {
        throw new DOMException('SecurityError')
      },
    }
    const result = withLocalStorage(throwingStorage, () => readStoredString('k', 'papi_24'))
    expect(result).toBe('papi_24')
  })
})

describe('initialRunwayId', () => {
  it('returns a persisted runway id over the default', () => {
    window.localStorage.setItem(STORAGE_KEYS.runway, 'custom_x')
    expect(initialRunwayId()).toBe('custom_x')
  })

  it('falls back to papi_24 when nothing is stored', () => {
    expect(initialRunwayId()).toBe('papi_24')
  })
})

describe('initialLanguage', () => {
  it('returns a persisted, supported language when present', () => {
    window.localStorage.setItem(STORAGE_KEYS.language, 'de')
    expect(initialLanguage()).toBe('de')
  })

  it('ignores a stored language that is not supported and falls through', () => {
    // 'xx' is not in SUPPORTED_LANGUAGES; readStoredChoice returns null, so we
    // fall through to navigator.language detection (jsdom default is en-US).
    window.localStorage.setItem(STORAGE_KEYS.language, 'xx')
    const result = initialLanguage()
    // jsdom's navigator.language is 'en-US' -> 'en'.
    expect(result).toBe('en')
  })

  it('returns a 2-letter string in all cases', () => {
    const result = initialLanguage()
    expect(typeof result).toBe('string')
    expect(result).toHaveLength(2)
  })
})
