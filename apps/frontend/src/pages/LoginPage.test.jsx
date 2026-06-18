import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { LoginPage } from './LoginPage.jsx'

const copy = translations.en
const roots = []
const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set

function render(admin, initialEntries = ['/login']) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      <MemoryRouter initialEntries={initialEntries}>
        <LoginPage copy={copy} admin={admin} />
      </MemoryRouter>,
    )
  })
  roots.push([root, container])
  return container
}

function renderWithRoutes(admin, initialEntries = ['/login']) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route path="/login" element={<LoginPage copy={copy} admin={admin} />} />
          <Route path="/models" element={<main>Models destination</main>} />
          <Route path="/datasets" element={<main>Datasets destination</main>} />
        </Routes>
      </MemoryRouter>,
    )
  })
  roots.push([root, container])
  return container
}

function baseAdmin(overrides = {}) {
  return {
    isAdmin: false,
    user: null,
    checking: false,
    authConfig: {
      mode: 'local',
      password_login_enabled: true,
      api_key_enabled: false,
      supabase_enabled: false,
    },
    signIn: vi.fn().mockResolvedValue({}),
    unlockApiKey: vi.fn(),
    unlockOpen: vi.fn(),
    lock: vi.fn(),
    ...overrides,
  }
}

function fillInput(input, value) {
  valueSetter.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

afterEach(() => {
  roots.splice(0).forEach(([root, container]) =>
    act(() => {
      root.unmount()
      container.remove()
    }),
  )
})

describe('LoginPage', () => {
  it('submits email-password credentials through the admin auth hook', async () => {
    const admin = baseAdmin()
    const container = render(admin)
    const [email, password] = container.querySelectorAll('input')

    await act(async () => {
      fillInput(email, 'operator@example.com')
      fillInput(password, 'secret')
      container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(admin.signIn).toHaveBeenCalledWith({ email: 'operator@example.com', password: 'secret' })
  })

  it('offers the API-key fallback and trims the submitted key', async () => {
    const admin = baseAdmin({
      authConfig: {
        mode: 'local_supabase',
        password_login_enabled: true,
        api_key_enabled: true,
        supabase_enabled: true,
      },
    })
    const container = render(admin)
    act(() => container.querySelector('.login-methods button:last-child').click())

    const keyInput = container.querySelector('input[type="password"]')
    await act(async () => {
      fillInput(keyInput, '  break-glass  ')
      container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(admin.unlockApiKey).toHaveBeenCalledWith('break-glass')
  })

  it('opens admin access directly in open-local mode', async () => {
    const admin = baseAdmin({
      authConfig: {
        mode: 'open',
        password_login_enabled: false,
        api_key_enabled: false,
        supabase_enabled: false,
      },
    })
    const container = render(admin)

    await act(async () => {
      container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(admin.unlockOpen).toHaveBeenCalled()
  })

  it('redirects to the protected page that originally sent the user to login', async () => {
    const admin = baseAdmin()
    const container = renderWithRoutes(admin, [
      { pathname: '/login', state: { from: { pathname: '/datasets' } } },
    ])
    const [email, password] = container.querySelectorAll('input')

    await act(async () => {
      fillInput(email, 'operator@example.com')
      fillInput(password, 'secret')
      container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(container.textContent).toContain('Datasets destination')
  })

  it('keeps the operator on the login page and shows a readable error on failure', async () => {
    const admin = baseAdmin({
      signIn: vi.fn().mockRejectedValue(new Error('Invalid credentials')),
    })
    const container = renderWithRoutes(admin)
    const [email, password] = container.querySelectorAll('input')

    await act(async () => {
      fillInput(email, 'operator@example.com')
      fillInput(password, 'wrong')
      container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(container.textContent).toContain('Invalid credentials')
    expect(container.textContent).not.toContain('Models destination')
  })

  it('shows account management and signs out when already authenticated', () => {
    const admin = baseAdmin({
      isAdmin: true,
      user: { email: 'admin@example.com', provider: 'local', roles: ['admin'] },
    })
    const container = render(admin)

    expect(container.textContent).toContain(copy.login.activeTitle)
    expect(container.textContent).toContain('admin@example.com')

    act(() => container.querySelector('button.ghost-button--danger').click())
    expect(admin.lock).toHaveBeenCalled()
  })
})
