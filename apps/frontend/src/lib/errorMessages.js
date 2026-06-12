// Error-code → localized-message mapping for errors thrown by lib/api.js.
// api.js never sees the i18n `copy` object — it tags errors with a stable code
// (same pattern as MODEL_OPTIONS_ERROR_CODE) and the display sites translate
// here. The constant lives in THIS module (api.js imports it, not vice-versa)
// so test files that vi.mock('../lib/api') wholesale don't lose it.

export const REQUEST_TIMEOUT_ERROR_CODE = 'request-timeout'

/**
 * Translate a coded api error for display; non-coded errors pass through with
 * their original message (e.g. backend `detail` strings render verbatim).
 */
export function localizedErrorMessage(error, copy) {
  if (error?.code === REQUEST_TIMEOUT_ERROR_CODE) {
    return copy.errors.requestTimeout.replace('{seconds}', String(error.timeoutSeconds))
  }
  return error?.message ?? String(error)
}
