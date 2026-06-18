import { useCallback, useEffect, useState } from 'react'
import {
  clearAuthSession,
  fetchAuthConfig,
  fetchCurrentUser,
  getApiKey,
  getAuthSession,
  loginUser,
  logoutUser,
  setAdminKey,
} from '../lib/api'

// "Admin mode" remains the UI flag that reveals management routes. Credentials are
// now provider-backed: local/Supabase sessions use Authorization: Bearer, while
// the old X-API-Key path stays as a backwards-compatible fallback.
const ADMIN_MODE_KEY = 'papi.adminMode'
const DEFAULT_AUTH_CONFIG = {
  mode: 'auto',
  password_login_enabled: false,
  api_key_enabled: false,
  supabase_enabled: false,
}

function readAdminMode() {
  try {
    return window.localStorage.getItem(ADMIN_MODE_KEY) === '1'
  } catch {
    return false
  }
}

function writeAdminMode(enabled) {
  try {
    if (enabled) window.localStorage.setItem(ADMIN_MODE_KEY, '1')
    else window.localStorage.removeItem(ADMIN_MODE_KEY)
  } catch {
    /* accept the loss for this session */
  }
}

export function useAdminKey() {
  const [isAdmin, setIsAdmin] = useState(() => readAdminMode() || Boolean(getAuthSession()) || Boolean(getApiKey()))
  const [adminKey, setKey] = useState(() => getApiKey())
  const [session, setSession] = useState(() => getAuthSession())
  const [user, setUser] = useState(() => getAuthSession()?.user ?? null)
  const [authConfig, setAuthConfig] = useState(DEFAULT_AUTH_CONFIG)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    Promise.all([
      fetchAuthConfig().catch(() => DEFAULT_AUTH_CONFIG),
      fetchCurrentUser().catch(() => ({ authenticated: false })),
    ]).then(([config, currentUser]) => {
      if (!active) return
      const storedSession = getAuthSession()
      const key = getApiKey()
      const authenticated = Boolean(currentUser?.authenticated)
      setAuthConfig(config || DEFAULT_AUTH_CONFIG)
      setSession(storedSession)
      setKey(key)
      setUser(authenticated ? currentUser : storedSession?.user ?? null)
      setIsAdmin(
        readAdminMode()
        || Boolean(key)
        || Boolean(storedSession)
        || (authenticated && currentUser.provider !== 'open'),
      )
      setChecking(false)
    })
    return () => {
      active = false
    }
  }, [])

  const unlockApiKey = useCallback((key) => {
    const trimmed = (key || '').trim()
    if (trimmed) setAdminKey(trimmed)
    clearAuthSession()
    writeAdminMode(true)
    setIsAdmin(true)
    setKey(getApiKey())
    setSession(null)
    setUser(trimmed ? { authenticated: true, provider: 'api_key', roles: ['admin'] } : null)
    setError(null)
  }, [])

  const unlockOpen = useCallback(() => {
    setAdminKey(null)
    clearAuthSession()
    writeAdminMode(true)
    setIsAdmin(true)
    setKey(null)
    setSession(null)
    setUser({ authenticated: true, provider: 'open', roles: ['admin'] })
    setError(null)
  }, [])

  const signIn = useCallback(async ({ email, password }) => {
    setError(null)
    const nextSession = await loginUser({ email, password })
    writeAdminMode(true)
    setSession(nextSession)
    setUser(nextSession.user)
    setKey(null)
    setIsAdmin(true)
    return nextSession
  }, [])

  const lock = useCallback(() => {
    logoutUser().catch(() => {})
    writeAdminMode(false)
    setIsAdmin(false)
    setSession(null)
    setUser(null)
    setKey(null)
    setError(null)
  }, [])

  return {
    isAdmin,
    adminKey,
    session,
    user,
    authConfig,
    checking,
    error,
    setError,
    unlock: unlockApiKey,
    unlockApiKey,
    unlockOpen,
    signIn,
    lock,
  }
}
