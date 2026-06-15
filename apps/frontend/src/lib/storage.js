import { SUPPORTED_LANGUAGES } from '../i18n/translations'

// localStorage keys for the small persistence surface. Centralising them
// here keeps writes/reads in sync and makes them easy to grep.
export const STORAGE_KEYS = {
  theme: 'papi.theme.v2',
  language: 'papi.language',
  runway: 'papi.runway',
}

// Write a localStorage key, swallowing failures. Some browsers (Safari
// private mode) throw on setItem; the persisted choice is a nice-to-have,
// so we accept the loss for the session rather than crashing. This is the RAW
// writer (no consent gate) — use it only for strictly-necessary keys (the consent
// record itself). Non-essential preferences must go through ``setPreference``.
export function safeLocalStorageSet(key, value) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* localStorage not available — accept the loss for this session. */
  }
}

// Remove a localStorage key, swallowing failures (same private-mode/SSR caveats).
export function safeLocalStorageRemove(key) {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* nothing to clean up if storage is unavailable. */
  }
}

// --- Storage-consent gate -------------------------------------------------- //
// The app persists only FUNCTIONAL preferences (theme, language, runway) — no
// tracking, no analytics, no third parties. Even so, we ask before writing them so
// a visitor can keep the session ephemeral. The decision is itself stored (a
// strictly-necessary record, so we never re-ask) and versioned, so a future policy
// change can re-prompt by bumping the version.
export const CONSENT_KEY = 'papi.consent.v1'
const CONSENT_VERSION = 1
const CONSENT_DECISIONS = ['accepted', 'declined']

// 'accepted' | 'declined' | null (undecided / unreadable). Read fresh each call so
// a choice made in another tab (or in tests) is always reflected.
export function getConsentDecision() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(CONSENT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed && parsed.v === CONSENT_VERSION && CONSENT_DECISIONS.includes(parsed.decision)) {
      return parsed.decision
    }
    return null
  } catch {
    return null
  }
}

// Record the decision. On a refusal, also drop any preferences a prior 'accept'
// left behind, so declining genuinely stops us remembering anything.
export function setConsentDecision(decision) {
  if (!CONSENT_DECISIONS.includes(decision)) return
  safeLocalStorageSet(CONSENT_KEY, JSON.stringify({ v: CONSENT_VERSION, decision, ts: Date.now() }))
  if (decision === 'declined') {
    for (const key of Object.values(STORAGE_KEYS)) {
      safeLocalStorageRemove(key)
    }
  }
}

// Forget the decision so the banner is shown again (the "Cookie preferences" link).
export function resetConsentDecision() {
  safeLocalStorageRemove(CONSENT_KEY)
}

// Persist a NON-ESSENTIAL preference — honoured only once the visitor has accepted
// storage; otherwise the value lives in React state for the session and is never
// written to disk. Returns whether it was persisted.
export function setPreference(key, value) {
  if (getConsentDecision() !== 'accepted') return false
  safeLocalStorageSet(key, value)
  return true
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

// Initial theme: persisted value -> dark. Computed once via lazy initializer so
// the App doesn't re-read localStorage on every render. We intentionally do not
// follow the OS preference for first-time visitors: the night-ops dark theme is
// the product's primary presentation — detection overlays and the red/white lamp
// language read best on graphite — while an explicit user toggle still persists.
export function initialTheme() {
  const stored = readStoredChoice(STORAGE_KEYS.theme, ['light', 'dark'], null)
  if (stored) return stored
  return 'dark'
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
