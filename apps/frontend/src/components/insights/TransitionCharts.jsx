import { useMemo } from 'react'
import { ArrowLeftRight } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { axisTitle, basePlotLayout, baseAxisStyle, plotlyConfig, plotlyPalette } from '../../catalog/plotly'
import { transitionCountSeries } from '../../lib/insightsTransforms'

// Transition tracking surfaces for video analyses: a frame×light timeline, a
// per-light count bar, and an event table. Every value comes from the backend's
// transitions[] (lamp_index, from_state, to_state, frame_index, optional
// elevation_angle_deg). Timestamp / intermediate state / per-event confidence
// are NOT in the payload, so the table shows "—" for them — never fabricated.
// The transitionCountSeries transform lives in lib/insightsTransforms.js.

const LANE_COUNT = 4

function TransitionTimeline({ transitions, plotTheme, copy }) {
  const laneLabels = useMemo(
    () => Array.from({ length: LANE_COUNT }, (_, i) => `${copy.live.light} ${i + 1}`),
    [copy.live.light],
  )

  const markers = useMemo(() => {
    const xs = []
    const ys = []
    const colors = []
    const lines = []
    const hover = []
    for (const event of transitions) {
      const lampIndex = Math.min(Math.max(event.lamp_index, 1), LANE_COUNT)
      xs.push(event.frame_index)
      ys.push(`${copy.live.light} ${lampIndex}`)
      colors.push(event.to_state === 'white' ? plotlyPalette.white : plotlyPalette.red)
      lines.push(event.to_state === 'white' ? plotlyPalette.red : plotlyPalette.warn)
      const fromLabel = copy.status?.[event.from_state] ?? event.from_state
      const toLabel = copy.status?.[event.to_state] ?? event.to_state
      hover.push(
        `${copy.live.light} ${lampIndex}<br>${copy.insights.thFrame} ${event.frame_index}<br>${fromLabel} → ${toLabel}`,
      )
    }
    return { xs, ys, colors, lines, hover }
  }, [transitions, copy])

  const frames = transitions.map((event) => event.frame_index).filter(Number.isFinite)
  const minFrame = frames.length ? Math.min(...frames) : 0
  const maxFrame = frames.length ? Math.max(...frames) : 1
  const pad = Math.max(1, Math.round((maxFrame - minFrame || 1) * 0.08))

  return (
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
      layout={basePlotLayout(plotTheme, {
        height: 360,
        margin: { l: 78, r: 16, t: 10, b: 42 },
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.thFrame, plotTheme),
          range: [minFrame - pad, maxFrame + pad],
          gridcolor: plotTheme.grid,
          zeroline: false,
        }),
        yaxis: baseAxisStyle(plotTheme, {
          // Plotly's y-axis is bottom-up: categoryarray[0] sits at the bottom.
          // Reverse so the lanes read Light 1 (top) → Light 4 (bottom), matching
          // the transition table's row order and the rest of the app's "Light 1
          // first" convention.
          categoryorder: 'array',
          categoryarray: [...laneLabels].reverse(),
          gridcolor: plotTheme.grid,
        }),
        showlegend: false,
      })}
      useResizeHandler
    />
  )
}

function TransitionCountBar({ transitions, plotTheme, copy }) {
  const { lamps, counts } = useMemo(() => transitionCountSeries(transitions), [transitions])
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={[
        {
          type: 'bar',
          x: lamps.map((lamp) => `${copy.live.light} ${lamp}`),
          y: counts,
          marker: { color: plotTheme.accent },
          hovertemplate: `%{x}<br>${copy.insights.transitionCountAxis}: %{y}<extra></extra>`,
        },
      ]}
      layout={basePlotLayout(plotTheme, {
        height: 320,
        margin: { l: 48, r: 16, t: 10, b: 40 },
        xaxis: baseAxisStyle(plotTheme),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.transitionCountAxis, plotTheme),
          gridcolor: plotTheme.grid,
          dtick: 1,
          rangemode: 'tozero',
        }),
      })}
      useResizeHandler
    />
  )
}

function TransitionTable({ transitions, copy }) {
  return (
    <div className="transition-table-wrap">
      <table className="transition-table" aria-labelledby="transition-table-heading">
        <thead>
          <tr>
            <th>{copy.insights.thLight}</th>
            <th>{copy.insights.thTimestamp}</th>
            <th className="num">{copy.insights.thFrame}</th>
            <th>{copy.insights.thFrom}</th>
            <th>{copy.insights.thTransition}</th>
            <th>{copy.insights.thTo}</th>
            <th className="num">{copy.insights.thAngle}</th>
            <th className="num">{copy.insights.thConfidence}</th>
          </tr>
        </thead>
        <tbody>
          {transitions.map((event, index) => (
            <tr key={`${event.lamp_index}-${event.frame_index}-${index}`}>
              <td>
                {copy.live.light} {event.lamp_index}
              </td>
              <td className="muted">—</td>
              <td className="num mono tnum">{event.frame_index}</td>
              <td>
                <span className={`state-pill is-${event.from_state}`}>
                  {copy.status?.[event.from_state] ?? event.from_state}
                </span>
              </td>
              <td className="muted">—</td>
              <td>
                <span className={`state-pill is-${event.to_state}`}>
                  {copy.status?.[event.to_state] ?? event.to_state}
                </span>
              </td>
              <td className="num mono tnum">
                {Number.isFinite(event.elevation_angle_deg)
                  ? event.elevation_angle_deg.toFixed(3)
                  : '—'}
              </td>
              <td className="num muted">—</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="viz-footnote">{copy.insights.transitionTableFootnote}</p>
    </div>
  )
}

export function TransitionCharts({ backendResults, plotTheme, copy }) {
  const transitions = useMemo(() => {
    const all = []
    for (const result of backendResults ?? []) {
      for (const event of result?.transitions ?? []) {
        all.push(event)
      }
    }
    return all
  }, [backendResults])

  if (!transitions.length) {
    return (
      <article className="viz-card">
        <div className="viz-heading">
          <ArrowLeftRight size={18} />
          <div>
            <h3>{copy.insights.transitionTimelineTitle}</h3>
            <p>{copy.insights.transitionTimelineText}</p>
          </div>
        </div>
        <AngleEmptyState
          icon={<ArrowLeftRight size={26} aria-hidden="true" />}
          message={copy.insights.transitionNone}
        />
      </article>
    )
  }

  return (
    <>
      <article className="viz-card span-all">
        <div className="viz-heading">
          <ArrowLeftRight size={18} />
          <div>
            <h3>{copy.insights.transitionTimelineTitle}</h3>
            <p>{copy.insights.transitionTimelineText}</p>
          </div>
        </div>
        <TransitionTimeline transitions={transitions} plotTheme={plotTheme} copy={copy} />
      </article>

      <article className="viz-card">
        <div className="viz-heading">
          <ArrowLeftRight size={18} />
          <div>
            <h3>{copy.insights.transitionCountTitle}</h3>
            <p>{copy.insights.transitionCountText}</p>
          </div>
        </div>
        <TransitionCountBar transitions={transitions} plotTheme={plotTheme} copy={copy} />
      </article>

      <article className="viz-card transition-table-card span-all">
        <div className="viz-heading">
          <ArrowLeftRight size={18} />
          <div>
            <h3 id="transition-table-heading">{copy.insights.transitionTableTitle}</h3>
            <p>{copy.insights.transitionTableText}</p>
          </div>
        </div>
        <TransitionTable transitions={transitions} copy={copy} />
      </article>
    </>
  )
}
