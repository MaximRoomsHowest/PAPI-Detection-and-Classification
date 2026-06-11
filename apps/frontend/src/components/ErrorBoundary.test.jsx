import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary.jsx'

function Boom() {
  throw new Error('render crash')
}

const mountedRoots = []

function render(element) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(element)
  })
  mountedRoots.push(root)
  return { container, root }
}

afterEach(() => {
  mountedRoots.splice(0).forEach((root) => {
    act(() => {
      root.unmount()
    })
  })
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ErrorBoundary', () => {
  it('renders children when nothing throws', () => {
    const { container } = render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    )
    expect(container.textContent).toContain('all good')
    expect(container.querySelector('[role="alert"]')).toBeNull()
  })

  it('shows the reload fallback when a child render crashes', () => {
    // The boundary logs the caught error on purpose; keep the test output clean.
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const reload = vi.fn()
    // window.location.reload is read-only in jsdom; swap the whole location.
    vi.stubGlobal('location', { ...window.location, reload })

    const { container } = render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )

    const fallback = container.querySelector('[role="alert"]')
    expect(fallback).not.toBeNull()
    // Hardcoded English BY DESIGN: the boundary has no i18n dependency so it
    // still renders when i18n itself is what crashed.
    expect(fallback.textContent).toContain('Something went wrong')
    expect(consoleError).toHaveBeenCalled()

    act(() => {
      fallback
        .querySelector('button')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
