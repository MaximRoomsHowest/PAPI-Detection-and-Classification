import { act, createRef } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../../i18n/translations.js'
import { HistoryDetailModal } from './HistoryDetailModal.jsx'

const copy = translations.en

const baseLog = {
  original_filename: 'approach.jpg',
  global_state: 'correct_glidepath',
  runway_id: 'papi_24',
  confidence: 0.91,
  processing_ms: 42,
  media_type: 'image',
  artifact_url: '/media/annotated/approach.png',
  lamps: [],
  detections: [{ class_id: 1, confidence: 0.93, track_id: 1 }],
  angle: { angle_available: false, elevation_angle_deg: null, angle_note: null },
}

function makeProps(overrides = {}) {
  return {
    selectedLog: baseLog,
    artifact: { key: baseLog.artifact_url, url: 'blob:artifact' },
    showRaw: false,
    onToggleRaw: vi.fn(),
    onClose: vi.fn(),
    modalRef: createRef(),
    runways: [],
    copy,
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

afterEach(() => {
  mountedRoots.splice(0).forEach((root) => {
    act(() => {
      root.unmount()
    })
  })
  document.body.replaceChildren()
  vi.clearAllMocks()
})

describe('HistoryDetailModal', () => {
  it('renders the artifact only when its key matches the open log', () => {
    const { container, root } = render(<HistoryDetailModal {...makeProps()} />)
    expect(container.querySelector('.history-artifact img').getAttribute('src')).toBe('blob:artifact')

    // A stale blob (resolved for a previously-open log) must never render here.
    act(() => {
      root.render(
        <HistoryDetailModal
          {...makeProps({ artifact: { key: '/media/annotated/other.png', url: 'blob:stale' } })}
        />,
      )
    })
    expect(container.querySelector('.history-artifact')).toBeNull()
  })

  it('renders a <video> for video logs and an <img> for images', () => {
    const { container, root } = render(
      <HistoryDetailModal
        {...makeProps({ selectedLog: { ...baseLog, media_type: 'video' } })}
      />,
    )
    expect(container.querySelector('.history-artifact video')).not.toBeNull()

    act(() => {
      root.render(<HistoryDetailModal {...makeProps()} />)
    })
    expect(container.querySelector('.history-artifact img')).not.toBeNull()
    expect(container.querySelector('.history-artifact video')).toBeNull()
  })

  it('shows the persisted video story: model, media, truncation, transitions', () => {
    const videoLog = {
      ...baseLog,
      media_type: 'video',
      frame_count: 48,
      model_id: 'transition',
      model_label: 'Transition classifier',
      drone_id: 'M4E-01',
      truncated_at_frame: 48,
      transition_method: 'model',
      transitions: [
        { lamp_index: 2, from_state: 'red', to_state: 'white', frame_index: 24 },
      ],
    }
    const { container } = render(<HistoryDetailModal {...makeProps({ selectedLog: videoLog })} />)
    const text = container.textContent

    expect(text).toContain('Transition classifier')
    expect(text).toContain(`${copy.history.mediaVideo} · 48`)
    expect(text).toContain('M4E-01')
    expect(container.querySelector('.result-truncation')?.textContent).toBe(
      copy.live.truncatedAnalysis.replace('{frames}', '48'),
    )
    const transitions = container.querySelector('.history-transitions')
    expect(transitions.textContent).toContain(
      copy.live.transitionMethodUsed.replace('{method}', copy.live.transitionMethodModel),
    )
    // Localized lamp colours, never the raw enums.
    expect(transitions.textContent).toContain(
      `${copy.live.light} 2: ${copy.status.red} → ${copy.status.white}`,
    )
  })

  it('hides the optional sections when the log has no such data', () => {
    const { container } = render(<HistoryDetailModal {...makeProps()} />)
    expect(container.querySelector('.history-transitions')).toBeNull()
    expect(container.querySelector('.result-truncation')).toBeNull()
    expect(container.textContent).not.toContain(copy.history.drone)
  })

  it('shows the decode-shortfall banner for a persisted partial decode', () => {
    const shortLog = {
      ...baseLog,
      media_type: 'video',
      frame_count: 120,
      decode_shortfall: 80,
    }
    const { container } = render(<HistoryDetailModal {...makeProps({ selectedLog: shortLog })} />)

    expect(container.querySelector('.result-truncation')?.textContent).toBe(
      copy.live.decodeShortfall.replace('{decoded}', '120').replace('{expected}', '200'),
    )
  })

  it('keeps the raw detections behind the disclosure toggle', () => {
    const onToggleRaw = vi.fn()
    const { container, root } = render(<HistoryDetailModal {...makeProps({ onToggleRaw })} />)

    expect(container.querySelector('#history-raw-detections')).toBeNull()
    const toggle = [...container.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === copy.history.showRaw,
    )
    act(() => {
      toggle.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(onToggleRaw).toHaveBeenCalledTimes(1)

    act(() => {
      root.render(<HistoryDetailModal {...makeProps({ showRaw: true })} />)
    })
    const raw = container.querySelector('#history-raw-detections')
    expect(raw).not.toBeNull()
    expect(raw.textContent).toContain('"class_id": 1')
  })
})
