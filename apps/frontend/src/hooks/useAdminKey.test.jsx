import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAdminKey } from './useAdminKey.js'

const apiMocks = vi.hoisted(() => ({
  clearAuthSession: vi.fn(),
  fetchAuthConfig: vi.fn(),
  fetchCurrentUser: vi.fn(),
  getApiKey: vi.fn(),
  getAuthSession: vi.fn(),
  loginUser: vi.fn(),
  logoutUser: vi.fn(),
  setAdminKey: vi.fn(),
}))

vi.mock('../lib/api', () => apiMocks)

const roots = []
const defaultConfig = {
  mode: 'local',
  password_login_enabled: true,
  api_key_enabled: false,
  supabase_enabled: false,
}

function AdminProbe() {
  const admin = useAdminKey()
  return (
    <section>
      <output data-testid="checking">{admin.checking ? 'checking' : 'ready'}</output>
      <output data-testid="admin">{admin.isAdmin ? 'admin' : 'public'}</output>
      <output data-testid="mode">{admin.authConfig.mode}</output>
      <output data-testid="email">{admin.user?.email || ''}</output>
      <button type="button" onClick={() => admin.signIn({ email: 'operator@example.com', password: 'secret' })}>
        sign in
      </button>
      <button type="button" onClick={() => admin.unlockApiKey('  api-key  ')}>
        api key
      </button>
      <button type="button" onClick={admin.unlockOpen}>
        open
      </button>
      <button type="button" onClick={admin.lock}>
        lock
      </button>
    </section>
  )
}

function renderProbe() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(<AdminProbe />)
  })
  roots.push([root, container])
  return container
}

async function flushEffects() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

beforeEach(() => {
  window.localStorage.clear()
  apiMocks.clearAuthSession.mockClear()
  apiMocks.fetchAuthConfig.mockReset().mockResolvedValue(defaultConfig)
  apiMocks.fetchCurrentUser.mockReset().mockResolvedValue({ authenticated: false })
  apiMocks.getApiKey.mockReset().mockReturnValue(null)
  apiMocks.getAuthSession.mockReset().mockReturnValue(null)
  apiMocks.loginUser.mockReset().mockResolvedValue({
    access_token: 'session-token',
    user: { authenticated: true, email: 'operator@example.com', provider: 'local', roles: ['admin'] },
  })
  apiMocks.logoutUser.mockReset().mockResolvedValue({})
  apiMocks.setAdminKey.mockClear()
})

afterEach(() => {
  roots.splice(0).forEach(([root, container]) =>
    act(() => {
      root.unmount()
      container.remove()
    }),
  )
  window.localStorage.clear()
})

describe('useAdminKey', () => {
  it('loads auth config and keeps public state when no current user is authenticated', async () => {
    const container = renderProbe()

    await flushEffects()

    expect(container.querySelector('[data-testid="checking"]').textContent).toBe('ready')
    expect(container.querySelector('[data-testid="admin"]').textContent).toBe('public')
    expect(container.querySelector('[data-testid="mode"]').textContent).toBe('local')
    expect(apiMocks.fetchAuthConfig).toHaveBeenCalledTimes(1)
    expect(apiMocks.fetchCurrentUser).toHaveBeenCalledTimes(1)
  })

  it('promotes a verified non-open current user into admin mode', async () => {
    apiMocks.fetchCurrentUser.mockResolvedValueOnce({
      authenticated: true,
      email: 'operator@example.com',
      provider: 'supabase',
      roles: ['admin'],
    })
    const container = renderProbe()

    await flushEffects()

    expect(container.querySelector('[data-testid="admin"]').textContent).toBe('admin')
    expect(container.querySelector('[data-testid="email"]').textContent).toBe('operator@example.com')
  })

  it('updates state after password sign-in and lock clears the session view', async () => {
    const container = renderProbe()
    await flushEffects()

    await act(async () => {
      container.querySelector('button').click()
      await Promise.resolve()
    })

    expect(apiMocks.loginUser).toHaveBeenCalledWith({
      email: 'operator@example.com',
      password: 'secret',
    })
    expect(container.querySelector('[data-testid="admin"]').textContent).toBe('admin')
    expect(container.querySelector('[data-testid="email"]').textContent).toBe('operator@example.com')
    expect(window.localStorage.getItem('papi.adminMode')).toBe('1')

    await act(async () => {
      [...container.querySelectorAll('button')].at(-1).click()
      await Promise.resolve()
    })

    expect(apiMocks.logoutUser).toHaveBeenCalledTimes(1)
    expect(container.querySelector('[data-testid="admin"]').textContent).toBe('public')
    expect(window.localStorage.getItem('papi.adminMode')).toBeNull()
  })

  it('supports legacy API-key and open-local unlock paths', async () => {
    const container = renderProbe()
    await flushEffects()
    const [, apiKeyButton, openButton] = container.querySelectorAll('button')
    apiMocks.getApiKey.mockReturnValue('api-key')

    act(() => {
      apiKeyButton.click()
    })
    expect(apiMocks.setAdminKey).toHaveBeenCalledWith('api-key')
    expect(apiMocks.clearAuthSession).toHaveBeenCalledTimes(1)
    expect(container.querySelector('[data-testid="admin"]').textContent).toBe('admin')

    act(() => {
      openButton.click()
    })
    expect(apiMocks.setAdminKey).toHaveBeenLastCalledWith(null)
    expect(container.querySelector('[data-testid="admin"]').textContent).toBe('admin')
  })
})
