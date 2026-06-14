import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
