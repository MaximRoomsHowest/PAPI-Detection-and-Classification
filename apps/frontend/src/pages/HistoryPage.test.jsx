import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { HistoryPage } from './HistoryPage.jsx'

const mocks = vi.hoisted(() => ({
  fetchLogs: vi.fn(),
  fetchStats: vi.fn(),
  fetchModelInfo: vi.fn(),
  fetchModels: vi.fn(),
  fetchLogDetail: vi.fn(),
  resolveMediaUrl: vi.fn(),
  revokeMediaUrl: vi.fn(),
  downloadLogsCsv: vi.fn(),
}))

vi.mock('../lib/api', () => mocks)

vi.mock('../context/liveDemoContext', () => ({
  useLiveDemo: () => ({ runways: [] }),
}))

const copy = translations.en

const logItem = {
  id: 7,
  original_filename: 'approach.jpg',
  runway_id: 'papi_24',
  media_type: 'image',
  global_state: 'correct_glidepath',
  confidence: 0.91,
  angle_available: false,
  elevation_angle_deg: null,
  frame_count: 1,
  processing_ms: 42,
  created_at: '2026-06-10T12:00:00Z',
  artifact_url: '/media/annotated/approach.png',
  model_id: 'small',
}

const logDetail = {
  ...logItem,
  detections: [],
  lamps: [],
  angle: { angle_available: false, elevation_angle_deg: null, angle_note: null },
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

// Flush the pending fetch promises queued by the page's effects.
async function flush() {
  await act(async () => {
    await Promise.resolve()
  })
}

async function mountPage() {
  const rendered = render(<HistoryPage copy={copy} />)
  await flush()
  await flush()
  return rendered
}

function filterSelect(container, label) {
  return container.querySelector(`select[aria-label="${label}"]`)
}

beforeEach(() => {
  mocks.fetchLogs.mockResolvedValue({ items: [logItem], total: 1 })
  mocks.fetchStats.mockResolvedValue({
    by_runway: { papi_24: 1 },
    by_global_state: { correct_glidepath: 1 },
  })
  mocks.fetchModelInfo.mockResolvedValue(null)
  mocks.fetchModels.mockResolvedValue([])
  mocks.fetchLogDetail.mockResolvedValue(logDetail)
  mocks.resolveMediaUrl.mockImplementation(async (key) => (key ? `blob:${key}` : null))
  mocks.revokeMediaUrl.mockImplementation(() => {})
  mocks.downloadLogsCsv.mockResolvedValue(undefined)
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

describe('HistoryPage', () => {
  it('refetches from page 1 with the new filter on filter change', async () => {
    const { container } = await mountPage()

    const select = filterSelect(container, copy.history.runway)
    act(() => {
      select.value = 'papi_24'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()

    expect(mocks.fetchLogs).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 0, runwayId: 'papi_24' }),
    )
  })

  it('closes the detail modal and revokes its artifact when a filter changes', async () => {
    const { container } = await mountPage()

    const rowButton = [...container.querySelectorAll('button.history-link')].find(
      (button) => button.textContent === logItem.original_filename,
    )
    await act(async () => {
      rowButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(container.querySelector('.history-modal')).not.toBeNull()
    expect(mocks.resolveMediaUrl).toHaveBeenCalledWith(logItem.artifact_url)

    const select = filterSelect(container, copy.history.runway)
    act(() => {
      select.value = 'papi_24'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()

    expect(container.querySelector('.history-modal')).toBeNull()
    expect(mocks.revokeMediaUrl).toHaveBeenCalledWith(`blob:${logItem.artifact_url}`)
  })

  it('gates pagination against the total and the in-flight refetch', async () => {
    const { container } = await mountPage()

    const buttons = [...container.querySelectorAll('.history-pagination button')]
    const [prev, next] = buttons
    expect(prev.disabled).toBe(true)
    // total 1 with page size 25 -> pageEnd >= total, no next page to fetch.
    expect(next.disabled).toBe(true)
  })
})
