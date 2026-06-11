import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../../i18n/translations.js'
import { ResultPanel } from './ResultPanel.jsx'

const mocks = vi.hoisted(() => ({ contextValue: null }))

vi.mock('../../context/liveDemoContext', () => ({
  useLiveDemo: () => mocks.contextValue,
}))

const copy = translations.en

function makeScenario(overrides = {}) {
  return {
    summary: 'white + white + red + red',
    stateId: 'correct',
    lamps: [],
    metrics: { boxConfidence: 94, latency: 42 },
    angleSummary: { available: false, sourceId: null },
    rawResult: {
      runway_id: 'papi_24',
      model_id: 'small',
      model_label: 'Small detector',
      model_role: 'detector',
    },
    transitions: [],
    ...overrides,
  }
}

function makeContext(scenarioOverrides = {}) {
  return {
    activeScenario: makeScenario(scenarioOverrides),
    activeState: { color: '#00a8e6', label: 'Correct glidepath', description: 'Stable' },
    runways: [{ id: 'papi_24', label: 'PAPI 24' }],
    selectedRunwayId: 'papi_24',
    backendScenario: { id: 'backend' },
    isAnalyzing: false,
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
  mocks.contextValue = null
})

describe('ResultPanel provenance', () => {
  it('names the telemetry source when telemetry resolved but the angle solve failed', () => {
    mocks.contextValue = makeContext({
      angleSummary: { available: false, sourceId: 'telemetry_file' },
    })

    const { container } = render(<ResultPanel copy={copy} />)

    const strip = container.querySelector('.result-provenance')
    expect(strip).not.toBeNull()
    expect(strip.textContent).toContain(
      copy.live.provenanceTelemetryUnused.replace(
        '{source}',
        copy.live.angleSource.telemetry_file,
      ),
    )
    expect(strip.textContent).toContain('PAPI 24')
  })

  it('claims "none" only when no telemetry source resolved at all', () => {
    mocks.contextValue = makeContext({
      angleSummary: { available: false, sourceId: null },
    })

    const { container } = render(<ResultPanel copy={copy} />)

    expect(container.querySelector('.result-provenance').textContent).toContain(
      copy.live.provenanceTelemetryNone,
    )
  })

  it('hides the provenance strip when the angle readout already shows the source', () => {
    mocks.contextValue = makeContext({
      angleSummary: {
        available: true,
        sourceId: 'file_metadata',
        value: '3.02',
        uncertainty: null,
        source: copy.live.angleSource.file_metadata,
        nearestLampDistanceM: null,
        plausible: true,
      },
    })

    const { container } = render(<ResultPanel copy={copy} />)

    expect(container.querySelector('.result-provenance')).toBeNull()
    expect(container.querySelector('.angle-readout').textContent).toContain('3.02')
  })

  it('shows the truncation alert when the backend stamped truncated_at_frame', () => {
    mocks.contextValue = makeContext({
      rawResult: { runway_id: 'papi_24', truncated_at_frame: 600 },
    })

    const { container } = render(<ResultPanel copy={copy} />)

    const alert = container.querySelector('.result-truncation')
    expect(alert).not.toBeNull()
    expect(alert.textContent).toBe(copy.live.truncatedAnalysis.replace('{frames}', '600'))
  })
})
