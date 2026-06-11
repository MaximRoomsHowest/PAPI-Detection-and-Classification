import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { VideoConfidenceChart } from './VideoConfidenceChart.jsx'

// Render-counting stub: the memo contract (identical props -> no Plotly re-render)
// is the whole point of this suite, so count how often the plot body runs and
// capture the last props for the hover-data assertions.
const mocks = vi.hoisted(() => ({
  renderCount: 0,
  lastProps: null,
}))

vi.mock('./insights/LazyPlot', () => ({
  LazyPlot: (props) => {
    mocks.renderCount += 1
    mocks.lastProps = props
    return <div className="plot-stub" />
  },
}))

const copy = translations.en
const plotTheme = {
  paper: 'rgba(0,0,0,0)',
  plot: 'rgba(25,42,61,0.035)',
  text: '#192a3d',
  strong: '#0c1d2d',
  muted: '#5a6b7d',
  grid: 'rgba(25, 42, 61, 0.16)',
  border: 'rgba(25, 42, 61, 0.18)',
  accent: '#00426e',
  accentSoft: 'rgba(0, 66, 110, 0.18)',
  track: 'rgba(25, 42, 61, 0.12)',
}
const perFrame = [
  { frame_index: 0, confidence: 0.93, state: 'correct_glidepath' },
  { frame_index: 1, confidence: 0.41, state: 'partially_visible' },
]

// Parent harness: re-rendering it with a new `tick` value re-renders the chart
// with the SAME prop identities — mirroring a Live-Demo progress tick, where the
// context value changes but the chart's perFrame/plotTheme/copy stay identical.
function Harness({ frames, tick = 0 }) {
  void tick
  return <VideoConfidenceChart perFrame={frames} plotTheme={plotTheme} copy={copy} />
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

beforeEach(() => {
  mocks.renderCount = 0
  mocks.lastProps = null
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

describe('VideoConfidenceChart', () => {
  it('skips the plot re-render when the parent re-renders with identical props', () => {
    const { root } = render(<Harness frames={perFrame} />)
    expect(mocks.renderCount).toBe(1)

    act(() => {
      root.render(<Harness frames={perFrame} tick={1} />)
    })

    expect(mocks.renderCount).toBe(1)
  })

  it('re-renders the plot when perFrame identity changes', () => {
    const { root } = render(<Harness frames={perFrame} />)
    expect(mocks.renderCount).toBe(1)

    act(() => {
      root.render(<Harness frames={[...perFrame]} />)
    })

    expect(mocks.renderCount).toBe(2)
  })

  it('maps per-frame states to localized hover labels with a raw-value fallback', () => {
    render(<Harness frames={perFrame} />)

    const trace = mocks.lastProps.data[0]
    expect(trace.x).toEqual([0, 1])
    expect(trace.y).toEqual([93, 41])
    // Mapped backend state -> localized catalog label; unmapped -> prettified raw.
    expect(trace.customdata).toEqual(['Correct glidepath', 'partially visible'])
  })
})
