import { describe, expect, it } from 'vitest'
import { translations } from '../i18n/translations.js'
import { REQUEST_TIMEOUT_ERROR_CODE, localizedErrorMessage } from './errorMessages.js'

function timeoutError(seconds) {
  const error = new Error('Backend did not respond within 60 s.')
  error.code = REQUEST_TIMEOUT_ERROR_CODE
  error.timeoutSeconds = seconds
  return error
}

describe('localizedErrorMessage', () => {
  it.each(['en', 'de', 'nl', 'fr'])(
    'localizes a coded timeout error with the seconds interpolated (%s)',
    (locale) => {
      const copy = translations[locale]
      const message = localizedErrorMessage(timeoutError(60), copy)
      expect(message).toBe(copy.errors.requestTimeout.replace('{seconds}', '60'))
      expect(message).toContain('60')
      expect(message).not.toContain('{seconds}')
    },
  )

  it('passes non-coded errors through with their original message', () => {
    const detail = new Error('Runway papi_24 not found')
    expect(localizedErrorMessage(detail, translations.en)).toBe('Runway papi_24 not found')
  })

  it('stringifies non-Error values instead of crashing', () => {
    expect(localizedErrorMessage('boom', translations.en)).toBe('boom')
  })
})
