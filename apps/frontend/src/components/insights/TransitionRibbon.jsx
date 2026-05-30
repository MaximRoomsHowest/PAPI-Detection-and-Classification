import { useMemo, useState } from 'react'
import { Activity } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { plotlyConfig, plotlyPalette } from '../../catalog/plotly'
import { statusCopy } from '../../catalog/statusCatalog'
import { transitionFrames } from '../../catalog/scenarios'

const LANE_COUNT = 4

// Shared flat-ruled "ribbon" chrome (HUD corner ticks + white/red/amber
// legend) so the real-data swimlane and the illustrative demo matrix read as
// the same component.
function RibbonShell({ copy, isDemo, footnote, children }) {
  return (
    <article className="viz-card transition-card">
      <div className="viz-heading">
        <Activity size={18} />
        <div>
          <h3>{copy.insights.transitionTitle}</h3>
          <p>{copy.insights.transitionText}</p>
        </div>
        {isDemo && <span className="demo-tag">{copy.insights.demoData}</span>}
      </div>

      <div className="ribbon-frame">
        <span className="ribbon-tick tl" aria-hidden="true" />
        <span className="ribbon-tick tr" aria-hidden="true" />
        <span className="ribbon-tick bl" aria-hidden="true" />
        <span className="ribbon-tick br" aria-hidden="true" />
        {children}
      </div>

      <div className="ribbon-legend" aria-hidden="true">
        <span>
          <i className="ribbon-dot dot-white" />
          {copy.insights.transitionLegendWhite}
        </span>
        <span>
          <i className="ribbon-dot dot-red" />
          {copy.insights.transitionLegendRed}
        </span>
        <span>
          <i className="ribbon-dot dot-now" />
          {copy.insights.transitionLegendNow}
        </span>
      </div>

      <div className="ribbon-readout">{footnote}</div>
    </article>
  )
}

// Real backend video result: render the sparse per-lamp switch events as a
// 4-lane swimlane. The payload (activeScenario.transitions, built by
// scenarioFromBackendResult from backend transitions[]) is a sparse list of
// red<->white change-events with a real frame_index — NOT a dense per-frame
// grid — so we plot one marker per event and never synthesise cells.
function RealRibbon({ activeScenario, plotTheme, copy }) {
  const events = activeScenario.transitions
  const laneLabels = useMemo(
    () => Array.from({ length: LANE_COUNT }, (_, i) => `${copy.insights.transitionLamp} ${i + 1}`),
    [copy.insights.transitionLamp],
  )

  const markers = useMemo(() => {
    const xs = []
    const ys = []
    const colors = []
    const lines = []
    const hover = []
    for (const event of events) {
      const lampIndex = Math.min(Math.max(event.lamp_index, 1), LANE_COUNT)
      xs.push(event.frame_index)
      ys.push(`${copy.insights.transitionLamp} ${lampIndex}`)
      colors.push(event.to_state === 'white' ? plotlyPalette.white : plotlyPalette.red)
      lines.push(event.to_state === 'white' ? plotlyPalette.red : plotlyPalette.warn)
      const fromLabel = copy.status?.[event.from_state] ?? event.from_state
      const toLabel = copy.status?.[event.to_state] ?? event.to_state
      hover.push(
        `${copy.insights.transitionLamp} ${lampIndex}<br>${copy.insights.frame} ${event.frame_index}<br>${fromLabel} → ${toLabel}`,
      )
    }
    return { xs, ys, colors, lines, hover }
  }, [events, copy])

  const frames = events.map((event) => event.frame_index)
  const minFrame = Math.min(...frames)
  const maxFrame = Math.max(...frames)
  const pad = Math.max(1, Math.round((maxFrame - minFrame || 1) * 0.08))

  return (
    <RibbonShell
      copy={copy}
      isDemo={false}
      footnote={
        <>
          <span>{activeScenario.summary}</span>
          <strong className="mono tnum">
            {events.length} {copy.insights.transitionRealCount}
          </strong>
        </>
      }
    >
      <LazyPlot
        className="plotly-chart"
        config={plotlyConfig}
        data={[
          {
            type: 'scatter',
            mode: 'markers',
            x: markers.xs,
            y: markers.ys,
            text: markers.hover,
            hovertemplate: '%{text}<extra></extra>',
            marker: {
              size: 15,
              symbol: 'square',
              color: markers.colors,
              line: { color: markers.lines, width: 2 },
            },
          },
        ]}
        layout={{
          autosize: true,
          height: 360,
          margin: { l: 70, r: 18, t: 12, b: 40 },
          paper_bgcolor: plotTheme.paper,
          plot_bgcolor: plotTheme.paper,
          font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
          xaxis: {
            title: { text: copy.insights.frame, font: { color: plotTheme.muted, size: 11 } },
            range: [minFrame - pad, maxFrame + pad],
            gridcolor: plotTheme.grid,
            zeroline: false,
            fixedrange: true,
            tickfont: { color: plotTheme.muted },
          },
          yaxis: {
            categoryorder: 'array',
            categoryarray: [...laneLabels].reverse(),
            fixedrange: true,
            tickfont: { color: plotTheme.muted },
            gridcolor: plotTheme.grid,
          },
          showlegend: false,
        }}
        useResizeHandler
      />
    </RibbonShell>
  )
}

// No real transition data (image, folder, or no run yet): keep the illustrative
// demo matrix so the section is never empty on stage, but flag it 'Demo data'
// and surface the empty-state line so it is clearly not live model output.
function DemoRibbon({ activeScenario, plotTheme, copy }) {
  const [hovered, setHovered] = useState(2)
  const frame = transitionFrames[hovered]
  const statusToValue = { white: 0, transition: 1, red: 2 }
  const lampLabels = Array.from(
    { length: LANE_COUNT },
    (_, i) => `${copy.insights.transitionLamp} ${i + 1}`,
  )
  const frameLabels = transitionFrames.map((_, index) => `F${218 + index}`)
  const z = lampLabels.map((_, lampIndex) =>
    transitionFrames.map((frameStates) => statusToValue[frameStates[lampIndex]]),
  )
  const hoverText = lampLabels.map((lamp, lampIndex) =>
    transitionFrames.map((frameStates, frameIndex) => {
      const status = copy.status[frameStates[lampIndex]] ?? statusCopy[frameStates[lampIndex]].label
      return `${lamp}<br>${copy.insights.frame} ${218 + frameIndex}<br>${copy.insights.status}: ${status}`
    }),
  )

  return (
    <RibbonShell
      copy={copy}
      isDemo
      footnote={
        <>
          <span>{copy.insights.transitionEmpty}</span>
          <strong>
            {frame.filter((status) => status === 'transition').length > 0
              ? copy.insights.transitionDetected
              : activeScenario.summary}
          </strong>
        </>
      }
    >
      <LazyPlot
        className="plotly-chart"
        config={plotlyConfig}
        data={[
          {
            type: 'heatmap',
            x: frameLabels,
            y: lampLabels,
            z,
            text: hoverText,
            hovertemplate: '%{text}<extra></extra>',
            colorscale: [
              [0, plotlyPalette.white],
              [0.35, plotlyPalette.white],
              [0.5, plotlyPalette.transition],
              [0.68, plotlyPalette.transition],
              [0.84, plotlyPalette.red],
              [1, plotlyPalette.red],
            ],
            showscale: false,
            xgap: 6,
            ygap: 6,
          },
        ]}
        layout={{
          autosize: true,
          height: 360,
          margin: { l: 70, r: 18, t: 12, b: 40 },
          paper_bgcolor: plotTheme.paper,
          plot_bgcolor: plotTheme.paper,
          font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
          xaxis: { fixedrange: true, tickfont: { color: plotTheme.muted } },
          yaxis: {
            autorange: 'reversed',
            fixedrange: true,
            tickfont: { color: plotTheme.muted },
          },
          shapes: [
            {
              type: 'rect',
              xref: 'x',
              yref: 'paper',
              x0: frameLabels[hovered],
              x1: frameLabels[hovered],
              y0: 0,
              y1: 1,
              line: { color: plotlyPalette.warn, width: 3 },
            },
          ],
        }}
        onHover={(event) => {
          const nextIndex = frameLabels.indexOf(event.points[0].x)
          if (nextIndex >= 0) {
            setHovered(nextIndex)
          }
        }}
        useResizeHandler
      />
    </RibbonShell>
  )
}

export function TransitionRibbon({ activeScenario, plotTheme, copy }) {
  const hasRealTransitions =
    activeScenario.id === 'backend' && (activeScenario.transitions?.length ?? 0) > 0

  if (hasRealTransitions) {
    return <RealRibbon activeScenario={activeScenario} plotTheme={plotTheme} copy={copy} />
  }
  return <DemoRibbon activeScenario={activeScenario} plotTheme={plotTheme} copy={copy} />
}
