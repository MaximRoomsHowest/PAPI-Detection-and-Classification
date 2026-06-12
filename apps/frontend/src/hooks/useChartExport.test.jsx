import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useChartExport } from './useChartExport.js'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

// Renders the hook's error state and a trigger to set it, so the test can
// drive setExportError from an event handler (not during render).
function Harness({ copy }) {
  const { exportError, setExportError } = useChartExport(copy)
  return (
    <div>
      <span className="export-error">{exportError}</span>
      <button type="button" onClick={() => setExportError('boom')}>
        fail
      </button>
    </div>
  )
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
  vi.clearAllMocks()
})

describe('useChartExport', () => {
  it('clears the export error when the locale copy changes', () => {
    const copyEn = { insights: {} }
    const copyDe = { insights: {} }
    const { container, root } = render(<Harness copy={copyEn} />)

    act(() => {
      container.querySelector('button').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(container.querySelector('.export-error').textContent).toBe('boom')

    // Same copy identity -> the banner stays.
    act(() => {
      root.render(<Harness copy={copyEn} />)
    })
    expect(container.querySelector('.export-error').textContent).toBe('boom')

    // Locale switch (new copy identity) -> the stale banner is dropped.
    act(() => {
      root.render(<Harness copy={copyDe} />)
    })
    expect(container.querySelector('.export-error').textContent).toBe('')
  })
})
