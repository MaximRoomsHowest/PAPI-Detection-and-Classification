import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { useAnalysis } from './useAnalysis.js'

const mocks = vi.hoisted(() => ({
  analyzeFrame: vi.fn(),
  analyzeMedia: vi.fn(),
  analyzeSequence: vi.fn(),
  createRunway: vi.fn(),
  deleteRunway: vi.fn(),
  fetchModels: vi.fn(),
  fetchRunways: vi.fn(),
  resolveMediaUrl: vi.fn(),
  revokeMediaUrl: vi.fn(),
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('../lib/api', () => ({
  analyzeFrame: mocks.analyzeFrame,
  analyzeMedia: mocks.analyzeMedia,
  analyzeSequence: mocks.analyzeSequence,
  createRunway: mocks.createRunway,
  deleteRunway: mocks.deleteRunway,
  fetchModels: mocks.fetchModels,
  fetchRunways: mocks.fetchRunways,
  resolveMediaUrl: mocks.resolveMediaUrl,
  revokeMediaUrl: mocks.revokeMediaUrl,
}))

vi.mock('sonner', () => ({
  toast: mocks.toast,
}))

const copy = translations.en
const runway = {
  id: 'papi_24',
  label: 'PAPI 24',
  source: 'builtin',
  lights: [
    { point: 1, latitude: 47.673521, longitude: 9.518154, altitude_m: 461.37 },
    { point: 2, latitude: 47.67345, longitude: 9.518214, altitude_m: 461.37 },
    { point: 3, latitude: 47.67338, longitude: 9.518274, altitude_m: 461.37 },
    { point: 4, latitude: 47.673309, longitude: 9.518333, altitude_m: 461.37 },
  ],
}
const models = [
  { model_id: 'small', model_label: 'Small detector', available: true, is_default: true },
  { model_id: 'nano', model_label: 'Nano detector', available: true },
]

function analysisPayload(modelId = 'small') {
  return {
    log_id: `log-${modelId}`,
    media_type: 'image',
    original_filename: 'frame.jpg',
    runway_id: runway.id,
    model_id: modelId,
    model_label: modelId === 'nano' ? 'Nano detector' : 'Small detector',
    model_role: 'detector',
    global_state: 'correct_glidepath',
    lamps: [
      { index: 1, state: 'white', confidence: 0.92, bbox: [1, 1, 10, 10] },
      { index: 2, state: 'white', confidence: 0.91, bbox: [11, 1, 20, 10] },
      { index: 3, state: 'red', confidence: 0.9, bbox: [21, 1, 30, 10] },
      { index: 4, state: 'red', confidence: 0.89, bbox: [31, 1, 40, 10] },
    ],
    confidence: 0.9,
    frame_count: 1,
    processing_ms: 12,
    angle: { angle_available: false },
    artifact_url: null,
    detections: [],
    transitions: [],
    transition_method: 'tracking',
  }
}

function flush() {
  return new Promise((resolve) => window.setTimeout(resolve, 0))
}

async function waitForAssertion(assertion) {
  let lastError
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      assertion()
      return
    } catch (error) {
      lastError = error
      await act(async () => {
        await flush()
      })
    }
  }
  throw lastError
}

describe('useAnalysis inference triggering', () => {
  let root
  let latest

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:frame'),
      revokeObjectURL: vi.fn(),
    })
    mocks.fetchRunways.mockResolvedValue([runway])
    mocks.fetchModels.mockResolvedValue(models)
    mocks.resolveMediaUrl.mockResolvedValue(null)
    mocks.analyzeFrame.mockImplementation(async (_file, metadata) => analysisPayload(metadata.modelId))
  })

  afterEach(() => {
    if (root) {
      act(() => root.unmount())
      root = null
    }
    document.body.replaceChildren()
    latest = null
    delete globalThis.IS_REACT_ACT_ENVIRONMENT
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  function renderHook() {
    const container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    function Harness() {
      latest = useAnalysis(copy)
      return null
    }

    act(() => {
      root.render(<Harness />)
    })
  }

  it('auto-runs backend inference after an image upload with the selected model id', async () => {
    renderHook()
    const file = new File(['image'], 'frame.jpg', { type: 'image/jpeg' })

    await act(async () => {
      latest.handleMediaFiles([file])
      await flush()
    })

    await waitForAssertion(() => {
      expect(mocks.analyzeFrame).toHaveBeenCalledTimes(1)
    })
    expect(mocks.analyzeFrame.mock.calls[0][1]).toMatchObject({
      runwayId: runway.id,
      modelId: 'small',
    })
  })

  it('re-runs the existing upload when the inference model changes', async () => {
    renderHook()
    const file = new File(['image'], 'frame.jpg', { type: 'image/jpeg' })

    await act(async () => {
      latest.handleMediaFiles([file])
      await flush()
    })
    await waitForAssertion(() => {
      expect(mocks.analyzeFrame).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      latest.setSelectedModelId('nano')
      await flush()
    })

    await waitForAssertion(() => {
      expect(mocks.analyzeFrame).toHaveBeenCalledTimes(2)
    })
    expect(mocks.analyzeFrame.mock.calls[1][1]).toMatchObject({
      runwayId: runway.id,
      modelId: 'nano',
    })
  })
})
