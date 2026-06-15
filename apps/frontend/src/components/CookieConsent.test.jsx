import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { CookieConsent } from './CookieConsent.jsx'

const copy = translations.en
const roots = []

function render(element) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => root.render(element))
  roots.push([root, container])
  return container
}

afterEach(() => {
  roots.splice(0).forEach(([root, container]) =>
    act(() => {
      root.unmount()
      container.remove()
    }),
  )
})

function fakeConsent(overrides = {}) {
  return { decision: null, decided: false, accept: vi.fn(), decline: vi.fn(), reopen: vi.fn(), ...overrides }
}

describe('CookieConsent', () => {
  it('shows a real, informative banner while undecided', () => {
    const container = render(<CookieConsent copy={copy} consent={fakeConsent()} />)
    expect(container.querySelector('[role="dialog"]')).not.toBeNull()
    expect(container.textContent).toContain(copy.cookie.title)
    expect(container.textContent).toContain(copy.cookie.message) // explains what's stored
    expect(container.textContent).toContain(copy.cookie.accept)
    expect(container.textContent).toContain(copy.cookie.decline)
  })

  it('renders nothing once a decision has been made (no re-nag)', () => {
    const container = render(
      <CookieConsent copy={copy} consent={fakeConsent({ decision: 'accepted', decided: true })} />,
    )
    expect(container.textContent).toBe('')
  })

  it('wires Allow/Decline to the consent handlers', () => {
    const consent = fakeConsent()
    const container = render(<CookieConsent copy={copy} consent={consent} />)
    const [accept, decline] = container.querySelectorAll('.cookie-card__actions button')
    act(() => accept.click())
    expect(consent.accept).toHaveBeenCalledTimes(1)
    act(() => decline.click())
    expect(consent.decline).toHaveBeenCalledTimes(1)
  })

  it('Escape declines (necessary-only) so keyboard users are not trapped', () => {
    const consent = fakeConsent()
    const container = render(<CookieConsent copy={copy} consent={consent} />)
    act(() => {
      container
        .querySelector('[role="dialog"]')
        .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })
    expect(consent.decline).toHaveBeenCalledTimes(1)
  })
})
