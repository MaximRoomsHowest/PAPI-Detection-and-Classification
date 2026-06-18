import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { ModelsPage } from './ModelsPage.jsx'
import { DatasetsPage } from './DatasetsPage.jsx'

const mocks = vi.hoisted(() => ({
  models: {
    models: [],
    loading: false,
    error: null,
    upload: vi.fn(),
    promote: vi.fn(),
    setDisabled: vi.fn(),
    remove: vi.fn(),
    evaluate: vi.fn(),
    refetch: vi.fn(),
  },
  datasets: {
    datasets: [],
    loading: false,
    error: null,
    uploadBundle: vi.fn(),
    startAssisted: vi.fn(),
    remove: vi.fn(),
    refetch: vi.fn(),
  },
  jobs: { jobs: [], cancel: vi.fn(), refetch: vi.fn() },
}))

vi.mock('../hooks/useModelManagement', () => ({ useModelManagement: () => mocks.models }))
vi.mock('../hooks/useDatasets', () => ({ useDatasets: () => mocks.datasets }))
vi.mock('../hooks/useJobs', () => ({ useJobs: () => mocks.jobs }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const copy = translations.en

function renderPage(element) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(element)
  })
  return {
    container,
    unmount: () =>
      act(() => {
        root.unmount()
        container.remove()
      }),
  }
}

// Reset the shared hoisted mock list state before every test — vi.clearAllMocks()
// only clears spy call history, NOT object properties, so a test that mutates
// mocks.models.models must not leak into the next one (test isolation).
beforeEach(() => {
  mocks.models.models = []
  mocks.datasets.datasets = []
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('ModelsPage', () => {
  it('shows the admin gate when not unlocked', () => {
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin={false} />)
    expect(container.textContent).toContain(copy.models.adminRequired)
    unmount()
  })

  it('renders the registry surface when unlocked', () => {
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin />)
    expect(container.textContent).toContain(copy.models.title)
    expect(container.textContent).toContain(copy.models.empty)
    unmount()
  })

  it('keeps "Set default" reachable on a non-default model even when its weights are missing', () => {
    // Regression: the promote button used to require model.available, so once the
    // default landed on the only available model, no other card could be promoted —
    // there was no way to change the default again. It now shows on any non-default,
    // non-disabled model (matching the backend, which only refuses disabled ones).
    mocks.models.models = [
      {
        model_id: 'a',
        model_label: 'Serving detector',
        model_role: 'detector',
        source: 'builtin',
        is_default: true,
        available: true,
        disabled: false,
        protected: true,
        val_metrics: null,
      },
      {
        model_id: 'b',
        model_label: 'Spare detector',
        model_role: 'detector',
        source: 'uploaded',
        is_default: false,
        available: false,
        disabled: false,
        protected: false,
        val_metrics: null,
      },
    ]
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin />)
    expect(container.textContent).toContain(copy.models.actions.promote)
    unmount()
  })

  it('hides "Set default" on a disabled model (matching the backend, which refuses it)', () => {
    mocks.models.models = [
      { model_id: 'a', model_label: 'Default', model_role: 'detector', source: 'builtin', is_default: true, available: true, disabled: false, protected: true, val_metrics: null },
      { model_id: 'b', model_label: 'Disabled', model_role: 'detector', source: 'uploaded', is_default: false, available: true, disabled: true, protected: false, val_metrics: null },
    ]
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin />)
    // Neither the default (a) nor the disabled (b) model offers promote.
    expect(container.textContent).not.toContain(copy.models.actions.promote)
    unmount()
  })

  it('renders without crashing when datasets are loaded and the Evaluate dialog is closed', () => {
    // Regression: EvaluateModal derives a default dataset on every render via
    // pickDefaultDataset(ready, model). With ready datasets present and the dialog
    // closed (model === null), classCountOf(null) threw and blanked the whole page.
    // The empty-datasets default in other tests masked this (ready was [] → early return).
    mocks.models.models = [
      { model_id: 'a', model_label: 'Detector', model_role: 'detector', source: 'builtin', is_default: true, available: true, disabled: false, protected: true, val_metrics: null },
    ]
    mocks.datasets.datasets = [
      { id: 'builtin-detector-redwhite', name: 'Built-in', source: 'builtin', status: 'ready', class_names: { 0: 'red', 1: 'white' }, n_train: 0, n_val: 0, n_test: 10 },
    ]
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin />)
    expect(container.textContent).toContain(copy.models.title)
    unmount()
  })

  it('renders the per-condition weather robustness bars when weather_metrics is present', () => {
    mocks.models.models = [
      {
        model_id: 'nano-weather',
        model_label: 'Weather nano',
        model_role: 'detector',
        source: 'builtin',
        is_default: false,
        available: true,
        disabled: false,
        protected: false,
        val_metrics: { map50: 0.947 },
        weather_metrics: { severity: 'medium', split: 'test', clear: 0.948, rain: 0.951, fog: 0.946, haze: 0.944, snow: 0.882 },
      },
    ]
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin />)
    expect(container.textContent).toContain(copy.models.weather.title)
    for (const cond of ['clear', 'rain', 'fog', 'haze', 'snow']) {
      expect(container.textContent).toContain(copy.models.weather[cond])
    }
    // The decisive snow value is shown, formatted to three decimals by metricValue.
    expect(container.textContent).toContain('0.882')
    unmount()
  })

  it('omits the weather section when a model has no weather_metrics', () => {
    mocks.models.models = [
      { model_id: 'x', model_label: 'Plain', model_role: 'detector', source: 'builtin', is_default: true, available: true, disabled: false, protected: true, val_metrics: { map50: 0.9 } },
    ]
    const { container, unmount } = renderPage(<ModelsPage copy={copy} isAdmin />)
    expect(container.textContent).not.toContain(copy.models.weather.title)
    unmount()
  })
})

describe('DatasetsPage', () => {
  it('shows the admin gate when not unlocked', () => {
    const { container, unmount } = renderPage(<DatasetsPage copy={copy} isAdmin={false} />)
    expect(container.textContent).toContain(copy.models.adminRequired)
    unmount()
  })

  it('renders the datasets surface when unlocked', () => {
    const { container, unmount } = renderPage(<DatasetsPage copy={copy} isAdmin />)
    expect(container.textContent).toContain(copy.datasets.title)
    expect(container.textContent).toContain(copy.datasets.empty)
    unmount()
  })
})
