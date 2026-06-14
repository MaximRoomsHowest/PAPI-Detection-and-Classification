import { useCallback, useState } from 'react'
import { getApiKey, setAdminKey } from '../lib/api'

// "Admin mode" is a UI flag (show the management surface) kept separate from the
// API key itself: an OPEN local deployment (no PAPI_API_KEY) still wants the
// management pages, while a GATED deployment also needs the key for X-API-Key.
// Entering a key implies admin mode; admin mode can also be on with no key (open).
const ADMIN_MODE_KEY = 'papi.adminMode'

function readAdminMode() {
  try {
    return window.localStorage.getItem(ADMIN_MODE_KEY) === '1'
  } catch {
    return false
  }
}

export function useAdminKey() {
  const [isAdmin, setIsAdmin] = useState(readAdminMode)
  const [adminKey, setKey] = useState(() => getApiKey())

  const unlock = useCallback((key) => {
    const trimmed = (key || '').trim()
    if (trimmed) setAdminKey(trimmed)
    try {
      window.localStorage.setItem(ADMIN_MODE_KEY, '1')
    } catch {
      /* accept the loss for this session */
    }
    setIsAdmin(true)
    setKey(getApiKey())
  }, [])

  const lock = useCallback(() => {
    setAdminKey(null)
    try {
      window.localStorage.removeItem(ADMIN_MODE_KEY)
    } catch {
      /* accept the loss for this session */
    }
    setIsAdmin(false)
    setKey(null)
  }, [])

  return { isAdmin, adminKey, unlock, lock }
}
