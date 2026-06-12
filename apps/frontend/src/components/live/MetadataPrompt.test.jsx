import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../../i18n/translations.js'
import { FOLDER_MODE_ANGLE_SWEEP } from '../../lib/analysisMode.js'
import { MetadataPrompt } from './MetadataPrompt.jsx'

const mocks = vi.hoisted(() => ({ contextValue: null }))

vi.mock('../../context/liveDemoContext', () => ({
  useLiveDemo: () => mocks.contextValue,
}))

const copy = translations.en

function makeContext(telemetry, overrides = {}) {
  return {
    activeScenario: { angleSummary: { available: false, sourceId: null } },
    backendScenario: { id: 'backend' },
    media: { type: 'image', url: 'blob:frame', file: {} },
    runways: [{ id: 'papi_24', label: 'PAPI 24' }],
    selectedRunwayId: 'papi_24',
    setSelectedRunwayId: vi.fn(),
    droneTelemetry: telemetry,
    setDroneTelemetry: vi.fn(),
    droneId: '',
    setDroneId: vi.fn(),
    metadataFile: null,
    setMetadataFile: vi.fn(),
    folderMode: FOLDER_MODE_ANGLE_SWEEP,
    runBackendInference: vi.fn(),
    isAnalyzing: false,
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

function applyButton(container) {
  return container.querySelector('.metadata-prompt__apply')
}

afterEach(() => {
  mountedRoots.splice(0).forEach((root) => {
    act(() => {
      root.unmount()
    })
  })
  document.body.replaceChildren()
  vi.clearAllMocks()
  mocks.contextValue = null
})

describe('MetadataPrompt manual-position validation', () => {
  it('blocks Apply and flags the offending field for a non-numeric value', () => {
    mocks.contextValue = makeContext({ latitude: 'abc', longitude: '9.5', altitudeM: '520' })

    const { container } = render(<MetadataPrompt copy={copy} />)

    expect(applyButton(container).disabled).toBe(true)
    expect(container.querySelector('.drone-telemetry__invalid')?.textContent).toBe(
      copy.live.telemetryInvalidHint,
    )
    expect(container.querySelector('#drone-latitude').getAttribute('aria-invalid')).toBe('true')
    expect(container.querySelector('#drone-longitude').getAttribute('aria-invalid')).toBe('false')
  })

  it('blocks Apply for an out-of-range latitude', () => {
    mocks.contextValue = makeContext({ latitude: '95', longitude: '9.5', altitudeM: '520' })

    const { container } = render(<MetadataPrompt copy={copy} />)

    expect(applyButton(container).disabled).toBe(true)
    expect(container.querySelector('#drone-latitude').getAttribute('aria-invalid')).toBe('true')
  })

  it('enables Apply for a complete in-range position', () => {
    mocks.contextValue = makeContext({ latitude: '47.665', longitude: '9.505', altitudeM: '520' })

    const { container } = render(<MetadataPrompt copy={copy} />)

    expect(applyButton(container).disabled).toBe(false)
    expect(container.querySelector('.drone-telemetry__invalid')).toBeNull()
  })

  it('accepts altitudes the backend accepts (bounds mirror ALTITUDE_MAX_M = 20000)', () => {
    // A stale 15000 m client cap used to block 15000–20000 m values that the
    // backend — and the field's own hint text — accept (audit 2026-06-12).
    mocks.contextValue = makeContext({ latitude: '47.665', longitude: '9.505', altitudeM: '16000' })

    const { container } = render(<MetadataPrompt copy={copy} />)

    expect(applyButton(container).disabled).toBe(false)
    expect(container.querySelector('#drone-altitude').getAttribute('aria-invalid')).toBe('false')
  })

  it('offers the optional drone-id input and forwards typing to the hook', () => {
    const setDroneId = vi.fn()
    mocks.contextValue = makeContext(
      { latitude: '', longitude: '', altitudeM: '' },
      { setDroneId },
    )

    const { container } = render(<MetadataPrompt copy={copy} />)

    const input = container.querySelector('#drone-id')
    expect(input).not.toBeNull()
    act(() => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
      setValue.call(input, 'M4E-01')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(setDroneId).toHaveBeenCalledWith('M4E-01')
  })

  it('keeps Apply gated (not flagged) while fields are simply empty', () => {
    mocks.contextValue = makeContext({ latitude: '', longitude: '', altitudeM: '' })

    const { container } = render(<MetadataPrompt copy={copy} />)

    expect(applyButton(container).disabled).toBe(true)
    expect(container.querySelector('.drone-telemetry__invalid')).toBeNull()
  })
})
