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
    image_count: 4,
    video_count: 6,
    avg_confidence: 0.59,
    // Internally consistent: overall avg = (4*320 + 6*12000) / 10 = 7328.
    avg_processing_ms: 7328,
    p50_processing_ms: 404,
    p95_processing_ms: 23714,
    // Latency is split by media type (a video spans many frames vs a single image).
    image_avg_processing_ms: 320,
    image_p50_processing_ms: 300,
    image_p95_processing_ms: 600,
    video_avg_processing_ms: 12000,
    video_p50_processing_ms: 9000,
    video_p95_processing_ms: 30000,
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

  it('still renders the latency chart when only one media type has data', async () => {
    mocks.fetchStats.mockResolvedValue({
      by_global_state: { correct_glidepath: 5 },
      total_analyses: 5,
      image_count: 5,
      video_count: 0,
      avg_processing_ms: 300,
      image_avg_processing_ms: 300,
      image_p50_processing_ms: 280,
      image_p95_processing_ms: 600,
      video_avg_processing_ms: null,
      video_p50_processing_ms: null,
      video_p95_processing_ms: null,
    })
    const { container } = render(<InferencePerformance plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()
    // Global-state distribution + latency (images-only) both render.
    expect(container.querySelectorAll('.plot-stub').length).toBe(2)
  })

  it('shows the latency empty state when no media has timing data', async () => {
    mocks.fetchStats.mockResolvedValue({
      by_global_state: { correct_glidepath: 2 },
      total_analyses: 2,
      image_count: 2,
      video_count: 0,
      avg_processing_ms: null,
      image_avg_processing_ms: null,
      image_p50_processing_ms: null,
      image_p95_processing_ms: null,
      video_avg_processing_ms: null,
      video_p50_processing_ms: null,
      video_p95_processing_ms: null,
    })
    const { container } = render(<InferencePerformance plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()
    // Only the global-state chart renders; the latency chart shows its empty state.
    expect(container.querySelectorAll('.plot-stub').length).toBe(1)
    expect(container.textContent).toContain(copy.insights.latencyEmpty)
  })

  it('surfaces a backend error in the section', async () => {
    mocks.fetchStats.mockRejectedValueOnce(new Error('boom'))
    const { container } = render(<InferencePerformance plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    expect(container.textContent).toContain(copy.insights.loadError)
  })
})
