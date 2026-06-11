import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../../i18n/translations.js'
import { ModelMetricsPanel } from './ModelMetricsPanel.jsx'

const mocks = vi.hoisted(() => ({
  fetchStats: vi.fn(),
  fetchModels: vi.fn(),
  fetchModelInfo: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  fetchStats: mocks.fetchStats,
  fetchModels: mocks.fetchModels,
  fetchModelInfo: mocks.fetchModelInfo,
}))

vi.mock('./LazyPlot', () => ({
  LazyPlot: () => <div className="plot-stub" />,
}))

const copy = translations.en
const plotTheme = { accent: '#00426e', accentSoft: 'rgba(0,66,110,0.2)', grid: '#ccc', muted: '#888', text: '#111', strong: '#000', paper: 'rgba(0,0,0,0)', plot: 'rgba(0,0,0,0)', border: '#ddd', track: '#eee' }

function card(modelId, overrides = {}) {
  return {
    model_id: modelId,
    model_label: `${modelId} label`,
    training_run: `${modelId}-run`,
    confidence_threshold: 0.4,
    val_metrics: { precision: 0.9, recall: 0.8, map50: 0.95, map50_95: 0.7 },
    ...overrides,
  }
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

async function flush() {
  await act(async () => {
    await Promise.resolve()
  })
}

beforeEach(() => {
  mocks.fetchStats.mockResolvedValue({ by_global_state: {}, total_analyses: 0 })
  mocks.fetchModels.mockResolvedValue([
    { model_id: 'small', model_label: 'Small detector', is_default: true, available: true },
    { model_id: 'transition', model_label: 'Transition classifier', available: false },
  ])
  mocks.fetchModelInfo.mockImplementation(async (modelId) => card(modelId ?? 'small'))
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

describe('ModelMetricsPanel model picker', () => {
  it('loads the backend default card first and marks it active', async () => {
    const { container } = render(<ModelMetricsPanel plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    expect(mocks.fetchModelInfo).toHaveBeenCalledWith(undefined)
    const active = container.querySelector('.model-selector__option.is-active')
    expect(active?.textContent).toBe('Small detector')
    expect(container.textContent).toContain('small-run')
  })

  it('fetches and shows another registry model on picker click — including unavailable ones', async () => {
    const { container } = render(<ModelMetricsPanel plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    const transitionButton = [...container.querySelectorAll('.model-selector__option')].find(
      (button) => button.textContent === 'Transition classifier',
    )
    act(() => {
      transitionButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    await flush()

    expect(mocks.fetchModelInfo).toHaveBeenLastCalledWith('transition')
    expect(container.textContent).toContain('transition-run')
    expect(transitionButton.getAttribute('aria-pressed')).toBe('true')
  })

  it('renders no picker when the registry has a single entry', async () => {
    mocks.fetchModels.mockResolvedValueOnce([
      { model_id: 'small', model_label: 'Small detector', is_default: true, available: true },
    ])
    const { container } = render(<ModelMetricsPanel plotTheme={plotTheme} copy={copy} />)
    await flush()
    await flush()

    expect(container.querySelector('.model-selector')).toBeNull()
  })
})
