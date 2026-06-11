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

  it('sends the media/date/confidence filters to the API and the CSV export', async () => {
    const { container } = await mountPage()

    const media = filterSelect(container, copy.history.media)
    act(() => {
      media.value = 'video'
      media.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    expect(mocks.fetchLogs).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 0, mediaType: 'video' }),
    )
    // The stats cards describe the same slice (and say so).
    expect(mocks.fetchStats).toHaveBeenLastCalledWith(
      expect.objectContaining({ mediaType: 'video' }),
    )
    expect(container.querySelector('.history-summary__scope')).not.toBeNull()

    const confidence = filterSelect(container, copy.history.confidence)
    act(() => {
      confidence.value = '0.75'
      confidence.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    expect(mocks.fetchLogs).toHaveBeenLastCalledWith(
      expect.objectContaining({ minConfidence: 0.75 }),
    )

    const date = container.querySelector('input[type="date"]')
    act(() => {
      // React's onChange listens to the native `input` event, and the value must
      // go through the prototype setter so React's value tracker sees the change.
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
      setValue.call(date, '2026-06-01')
      date.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await flush()
    // LOCAL midnight converted to a UTC instant — a bare date would be read as
    // UTC midnight server-side and silently drop early-morning local rows.
    const expectedInstant = new Date('2026-06-01T00:00:00').toISOString()
    expect(mocks.fetchLogs).toHaveBeenLastCalledWith(
      expect.objectContaining({ createdAfter: expectedInstant }),
    )

    // The CSV export reuses every active filter (and names the file after them).
    const exportButton = [...container.querySelectorAll('button')].find((button) =>
      button.textContent.includes(copy.history.exportCsv),
    )
    await act(async () => {
      exportButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(mocks.downloadLogsCsv).toHaveBeenCalledWith(
      expect.objectContaining({ mediaType: 'video', createdAfter: expectedInstant, minConfidence: 0.75 }),
      expect.stringContaining('video'),
    )

    // Clear filters resets all six and refetches unfiltered from page 1.
    const clear = [...container.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === copy.history.clearFilters,
    )
    act(() => {
      clear.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(mocks.fetchLogs).toHaveBeenLastCalledWith(
      expect.objectContaining({
        offset: 0,
        mediaType: undefined,
        createdAfter: undefined,
        minConfidence: undefined,
      }),
    )
  })

  it('restores focus to the row that opened the modal when it closes', async () => {
    const { container } = await mountPage()

    const rowButton = [...container.querySelectorAll('button.history-link')].find(
      (button) => button.textContent === logItem.original_filename,
    )
    // Keyboard path: the row is focused, then activated. The button must stay
    // focusable while the detail loads (aria-disabled, NOT disabled) or focus
    // drops to <body> before the modal opens and never comes back to the row.
    rowButton.focus()
    await act(async () => {
      rowButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(container.querySelector('.history-modal')).not.toBeNull()
    expect(rowButton.getAttribute('aria-disabled')).toBe('false')

    const closeButton = container.querySelector('.history-modal button.icon-button')
    act(() => {
      closeButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()

    expect(container.querySelector('.history-modal')).toBeNull()
    expect(document.activeElement).toBe(rowButton)
  })

  it('ignores a second row activation while a detail is already loading', async () => {
    let resolveDetail
    mocks.fetchLogDetail.mockImplementation(
      () => new Promise((resolve) => { resolveDetail = resolve }),
    )
    const { container } = await mountPage()

    const buttons = [...container.querySelectorAll('button.history-link')]
    act(() => {
      buttons[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    act(() => {
      buttons[0].dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(mocks.fetchLogDetail).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveDetail(logDetail)
    })
    await flush()
    expect(container.querySelector('.history-modal')).not.toBeNull()
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
