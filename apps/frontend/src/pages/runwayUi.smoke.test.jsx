import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { RunwaySelector } from '../components/live/RunwaySelector.jsx'
import { RunwaysPage } from './RunwaysPage.jsx'

const mocks = vi.hoisted(() => ({
  contextValue: null,
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('../context/liveDemoContext', () => ({
  useLiveDemo: () => mocks.contextValue,
}))

vi.mock('sonner', () => ({
  toast: mocks.toast,
}))

const copy = translations.en
const builtinRunway = {
  id: 'papi_24',
  label: 'PAPI 24',
  source: 'builtin',
  airport: 'EDNY',
  designation: '24',
  lights: [
    { point: 1, latitude: 47.673521, longitude: 9.518154, altitude_m: 461.37 },
    { point: 2, latitude: 47.67345, longitude: 9.518214, altitude_m: 461.37 },
    { point: 3, latitude: 47.67338, longitude: 9.518274, altitude_m: 461.37 },
    { point: 4, latitude: 47.673309, longitude: 9.518333, altitude_m: 461.37 },
  ],
}
const customRunway = {
  ...builtinRunway,
  id: 'custom_1',
  label: 'Custom 1',
  source: 'custom',
  airport: 'TEST',
  designation: '01',
}
const mountedRoots = []

function makeContext(overrides = {}) {
  return {
    runways: [builtinRunway],
    runwayLoading: false,
    runwayError: null,
    selectedRunwayId: builtinRunway.id,
    selectedRunway: builtinRunway,
    setSelectedRunwayId: vi.fn(),
    addRunway: vi.fn(),
    removeRunway: vi.fn(),
    refetchRunways: vi.fn(),
    ...overrides,
  }
}

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
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
  mocks.contextValue = null
})

describe('runway UI smoke', () => {
  it('shows runway load errors with a retry action on the Runways page', () => {
    const refetchRunways = vi.fn()
    mocks.contextValue = makeContext({
      runwayError: new Error('backend unavailable'),
      refetchRunways,
    })

    const { container } = render(<RunwaysPage copy={copy} />)

    expect(container.textContent).toContain('Could not load runways: backend unavailable')

    const retryButton = [...container.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === copy.runways.retry,
    )
    act(() => {
      retryButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(refetchRunways).toHaveBeenCalledTimes(1)
  })

  it('renders a newly available custom runway in the Live Demo selector', () => {
    const setSelectedRunwayId = vi.fn()
    mocks.contextValue = makeContext({
      runways: [builtinRunway, customRunway],
      selectedRunwayId: customRunway.id,
      selectedRunway: customRunway,
      setSelectedRunwayId,
    })

    const { container } = render(
      <MemoryRouter>
        <RunwaySelector copy={copy} />
      </MemoryRouter>,
    )
    const select = container.querySelector('select')

    expect(select.value).toBe(customRunway.id)
    expect([...select.options].map((option) => option.textContent)).toContain(customRunway.label)

    act(() => {
      select.value = builtinRunway.id
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })

    expect(setSelectedRunwayId).toHaveBeenCalledWith(builtinRunway.id)
  })

  it('confirms before deleting the active custom runway', async () => {
    const removeRunway = vi.fn(async () => {})
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    mocks.contextValue = makeContext({
      runways: [builtinRunway, customRunway],
      selectedRunwayId: customRunway.id,
      selectedRunway: customRunway,
      removeRunway,
    })

    const { container } = render(<RunwaysPage copy={copy} />)
    const deleteButton = container.querySelector(`button[aria-label="${copy.runways.deleteButton} ${customRunway.label}"]`)

    await act(async () => {
      deleteButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(confirm).toHaveBeenCalledWith(
      'Delete “Custom 1”? It will no longer be available for new analyses.',
    )
    expect(removeRunway).toHaveBeenCalledWith(customRunway.id)
  })
})
