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

  it('stabilizes noisy tracking transitions for persisted video logs', () => {
    const videoLog = {
      ...baseLog,
      media_type: 'video',
      frame_count: 60,
      transition_method: 'tracking',
      angle_track: [
        { frame_index: 26, elevation_angle_deg: 2.32, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 27, elevation_angle_deg: 2.37, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 28, elevation_angle_deg: 2.41, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 29, elevation_angle_deg: 2.46, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 30, elevation_angle_deg: 2.52, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 31, elevation_angle_deg: 2.57, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 32, elevation_angle_deg: 2.61, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 33, elevation_angle_deg: 2.66, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 47, elevation_angle_deg: 3.34, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 48, elevation_angle_deg: 3.39, lamps: [{ index: 1, state: 'red' }] },
        { frame_index: 49, elevation_angle_deg: 3.45, lamps: [{ index: 1, state: 'white' }] },
        { frame_index: 50, elevation_angle_deg: 3.48, lamps: [{ index: 1, state: 'white' }] },
      ],
      transitions: [
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 28 },
        { lamp_index: 1, from_state: 'white', to_state: 'red', frame_index: 29 },
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 32 },
        { lamp_index: 1, from_state: 'white', to_state: 'red', frame_index: 48 },
        { lamp_index: 1, from_state: 'red', to_state: 'white', frame_index: 49 },
      ],
    }

    const { container } = render(<HistoryDetailModal {...makeProps({ selectedLog: videoLog })} />)
    const transitions = container.querySelector('.history-transitions').textContent

    expect(transitions).toContain(`${copy.history.frames.toLowerCase()} 32`)
    expect(transitions).not.toContain(`${copy.history.frames.toLowerCase()} 28`)
    expect(transitions).not.toContain(`${copy.history.frames.toLowerCase()} 29`)
    expect(transitions).not.toContain(`${copy.history.frames.toLowerCase()} 48`)
    expect(transitions).not.toContain(`${copy.history.frames.toLowerCase()} 49`)
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
