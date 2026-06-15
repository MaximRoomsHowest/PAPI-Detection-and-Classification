import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
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

describe('CookieConsent', () => {
  it('shows the friendly cookie banner on mount', () => {
    const container = render(<CookieConsent copy={copy} />)
    expect(container.querySelector('.cookie-card')).not.toBeNull()
    expect(container.textContent).toContain(copy.cookie.title)
    expect(container.textContent).toContain(copy.cookie.message)
    expect(container.textContent).toContain(copy.cookie.accept)
    expect(container.textContent).toContain(copy.cookie.decline)
  })

  it('shows a short accepted toast after accepting', () => {
    const container = render(<CookieConsent copy={copy} />)
    const [accept] = container.querySelectorAll('.cookie-card__actions button')
    act(() => accept.click())
    expect(container.querySelector('.cookie-toast--accepted')).not.toBeNull()
    expect(container.textContent).toContain(copy.cookie.accepted)
    expect(container.textContent).not.toContain(copy.cookie.declined)
  })

  it('shows a short declined toast after declining', () => {
    const container = render(<CookieConsent copy={copy} />)
    const decline = container.querySelectorAll('.cookie-card__actions button')[1]
    act(() => decline.click())
    expect(container.querySelector('.cookie-toast--declined')).not.toBeNull()
    expect(container.textContent).toContain(copy.cookie.declined)
  })
})
