import { SUPPORTED_LANGUAGES } from '../i18n/translations'

// localStorage keys for the small persistence surface. Centralising them
// here keeps writes/reads in sync and makes them easy to grep.
export const STORAGE_KEYS = {
  theme: 'papi.theme',
  language: 'papi.language',
  runway: 'papi.runway',
}

// Write a localStorage key, swallowing failures. Some browsers (Safari
// private mode) throw on setItem; the persisted choice is a nice-to-have,
// so we accept the loss for the session rather than crashing.
export function safeLocalStorageSet(key, value) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* localStorage not available — accept the loss for this session. */
  }
}

// Read a localStorage key and validate against an allowlist. Falls back to
// the provided default for any read error (Safari private mode, SSR, etc.).
export function readStoredChoice(key, allowed, fallback) {
  if (typeof window === 'undefined') return fallback
  try {
    const value = window.localStorage.getItem(key)
    return value && allowed.includes(value) ? value : fallback
  } catch {
    return fallback
  }
}

// Initial theme: persisted value -> system preference -> light. Computed
// once via lazy initializer so the App doesn't re-read localStorage on
// every render.
export function initialTheme() {
  const stored = readStoredChoice(STORAGE_KEYS.theme, ['light', 'dark'], null)
  if (stored) return stored
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

// Initial language: persisted -> navigator.language two-letter prefix
// (when in our supported set) -> 'en'.
export function initialLanguage() {
  const stored = readStoredChoice(
    STORAGE_KEYS.language,
    SUPPORTED_LANGUAGES,
    null,
  )
  if (stored) return stored
  if (typeof navigator === 'undefined') return 'en'
  const detected = (navigator.language || '').slice(0, 2).toLowerCase()
  return SUPPORTED_LANGUAGES.includes(detected) ? detected : 'en'
}

// Read a localStorage string WITHOUT an allowlist — for values whose valid set is
// dynamic (runway ids: custom runways can't be enumerated here). Still guarded for
// read errors / empty values; the live runway list is the real validator.
export function readStoredString(key, fallback) {
  if (typeof window === 'undefined') return fallback
  try {
    const value = window.localStorage.getItem(key)
    return value || fallback
  } catch {
    return fallback
  }
}

// Initial runway selection: persisted id -> backend default ('papi_24'). The id is
// reconciled against the fetched runway list at runtime (a custom runway may have
// been deleted in another tab), so no static allowlist is applied here.
export function initialRunwayId() {
  return readStoredString(STORAGE_KEYS.runway, 'papi_24')
}
