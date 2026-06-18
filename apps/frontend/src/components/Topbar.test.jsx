import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { Topbar } from './Topbar.jsx'

const copy = translations.en
const roots = []

function renderTopbar(overrides = {}) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  const props = {
    copy,
    theme: 'light',
    onToggleTheme: vi.fn(),
    language: 'en',
    onSelectLanguage: vi.fn(),
    admin: {
      isAdmin: false,
      checking: false,
      user: null,
    },
    ...overrides,
  }
  act(() => {
    root.render(
      <MemoryRouter>
        <Topbar {...props} />
      </MemoryRouter>,
    )
  })
  roots.push([root, container])
  return { container, props }
}

afterEach(() => {
  roots.splice(0).forEach(([root, container]) =>
    act(() => {
      root.unmount()
      container.remove()
    }),
  )
})

describe('Topbar', () => {
  it('keeps management routes hidden until an operator is signed in', () => {
    const { container } = renderTopbar()

    expect(container.textContent).toContain(copy.nav.liveDemo)
    expect(container.textContent).toContain(copy.admin.signIn)
    expect(container.textContent).not.toContain(copy.nav.models)
    expect(container.textContent).not.toContain(copy.nav.datasets)
    expect(container.querySelector('.admin-access__button').getAttribute('href')).toBe('/login')
  })

  it('shows management routes and the operator account when signed in', () => {
    const { container } = renderTopbar({
      admin: {
        isAdmin: true,
        checking: false,
        user: { email: 'operator@example.com', provider: 'local', roles: ['admin'] },
      },
    })

    expect(container.textContent).toContain(copy.nav.models)
    expect(container.textContent).toContain(copy.nav.datasets)
    expect(container.textContent).toContain('operator@example.com')
    expect(container.querySelector('.admin-access__button--active')).not.toBeNull()
  })

  it('toggles theme and forwards language selections', () => {
    const onToggleTheme = vi.fn()
    const onSelectLanguage = vi.fn()
    const { container } = renderTopbar({ onToggleTheme, onSelectLanguage })

    act(() => {
      container.querySelector('.icon-button').click()
    })
    expect(onToggleTheme).toHaveBeenCalledTimes(1)

    act(() => {
      container.querySelector('.language-trigger').click()
    })
    const germanOption = [...container.querySelectorAll('.language-menu button')].find(
      (button) => button.textContent.includes('Deutsch'),
    )
    act(() => {
      germanOption.click()
    })

    expect(onSelectLanguage).toHaveBeenCalledWith('de')
    expect(container.querySelector('.language-menu')).toBeNull()
  })
})
