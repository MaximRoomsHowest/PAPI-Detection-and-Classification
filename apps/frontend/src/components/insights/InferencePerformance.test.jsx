import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../../i18n/translations.js'
import { InferencePerformance } from './InferencePerformance.jsx'

const mocks = vi.hoisted(() => ({
  fetchStats: vi.fn(),
  fetchModels: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  fetchStats: mocks.fetchStats,
  fetchModels: mocks.fetchModels,
}))

vi.mock('./LazyPlot', () => ({
  LazyPlot: () => <div className="plot-stub" />,
}))

const copy = translations.en
const plotTheme = { accent: '#00426e', accentSoft: 'rgba(0,66,110,0.2)', grid: '#ccc', muted: '#888', text: '#111', strong: '#000', paper: 'rgba(0,0,0,0)', plot: 'rgba(0,0,0,0)', border: '#ddd', track: '#eee' }

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

async function flush() {
  await act(async () => {
    await Promise.resolve()
  })
}

// Set a controlled <select>'s value past React's value tracker, then fire change.
function selectOption(select, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set
  setter.call(select, value)
  act(() => {
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

beforeEach(() => {
  mocks.fetchStats.mockResolvedValue({
    by_global_state: { correct_glidepath: 7, too_low: 3 },
    total_analyses: 10,
    avg_confidence: 0.59,
    avg_processing_ms: 7776,
    p50_processing_ms: 404,
    p95_processing_ms: 23714,
  })
  mocks.fetchModels.mockResolvedValue([
    { model_id: 'small', model_label: 'Small detector', is_default: true },
    { model_id: 'transition', model_label: 'Transition classifier' },
  ])
})

afterEach(() => {
  mountedRoots.splice(0).forEach((root) => {
    act(() => {
      root.unmount()
    })
  })
  document.body.replaceChildren()
  vi.clearAllMocks()
})

describe('InferencePerformance', () => {
  it('fetches unfiltered stats first and shows the count + charts', async () => {
    const { container } = render(<InferencePerformance plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    expect(mocks.fetchStats).toHaveBeenCalledWith({})
    // Two LazyPlot charts: global-state distribution + latency percentiles.
    expect(container.querySelectorAll('.plot-stub').length).toBe(2)
    expect(container.textContent).toContain('Showing 10 logged analyses')
  })

  it('re-fetches stats server-side when a filter changes', async () => {
    const { container } = render(<InferencePerformance plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    const mediaSelect = container.querySelector('select[aria-label="Media type"]')
    expect(mediaSelect).not.toBeNull()
    selectOption(mediaSelect, 'video')
    await flush()
    await flush()

    const lastArg = mocks.fetchStats.mock.calls.at(-1)[0]
    expect(lastArg.mediaType).toBe('video')
  })

  it('surfaces a backend error in the section', async () => {
    mocks.fetchStats.mockRejectedValueOnce(new Error('boom'))
    const { container } = render(<InferencePerformance plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    expect(container.textContent).toContain(copy.insights.loadError)
  })
})
