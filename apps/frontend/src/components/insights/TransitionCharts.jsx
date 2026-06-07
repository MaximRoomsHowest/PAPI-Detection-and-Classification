import { memo, useMemo } from 'react'
import { ArrowLeftRight } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import {
  axisTitle,
  basePlotLayout,
  baseAxisStyle,
  plotlyConfig,
  plotlyPalette,
  CHART_HEIGHT,
  integerTicks,
} from '../../catalog/plotly'
import { transitionCountSeries } from '../../lib/insightsTransforms'

// Transition tracking surfaces for video / folder-sequence analyses: a frame×light
// timeline, a per-light count bar, and an event table. Every value comes from the
// backend's transitions[] (lamp_index, from_state, to_state, frame_index, optional
// elevation_angle_deg, and — for the "model" method — method/start_frame/end_frame/
// duration_frames). Nothing is fabricated: a field that a given method doesn't
// produce shows "—".
const LANE_COUNT = 4

const clampLamp = (lampIndex) => Math.min(Math.max(lampIndex, 1), LANE_COUNT)

// Which method(s) produced these events, for the provenance badge (audit C3).
function methodLabel(transitions, copy) {
  const methods = [...new Set(transitions.map((event) => event.method ?? 'tracking'))]
  if (methods.length !== 1) {
    return copy.insights.transitionMethodMixed
  }
  const label = methods[0] === 'model' ? copy.live.transitionMethodModel : copy.live.transitionMethodTracking
  return copy.live.transitionMethodUsed.replace('{method}', label)
}

function eventHover(event, copy) {
  const lampIndex = clampLamp(event.lamp_index)
  const fromLabel = copy.status?.[event.from_state] ?? event.from_state
  const toLabel = copy.status?.[event.to_state] ?? event.to_state
  const lines = [
    `${copy.live.light} ${lampIndex}`,
    `${copy.insights.thFrame} ${event.frame_index}`,
    `${fromLabel} → ${toLabel}`,
  ]
  if (Number.isFinite(event.duration_frames)) {
    lines.push(`${copy.insights.thDuration}: ${event.duration_frames}`)
  }
  return lines.join('<br>')
}

// One marker trace per direction, distinguished by marker SYMBOL (not colour alone),
// so direction survives greyscale / the static PDF export / colour-vision deficiency,
// and a real legend explains it (audit B4).
function directionTrace(events, { symbol, fill, outline, name }, copy) {
  return {
    type: 'scatter',
    mode: 'markers',
    name,
    x: events.map((event) => event.frame_index),
    y: events.map((event) => `${copy.live.light} ${clampLamp(event.lamp_index)}`),
    text: events.map((event) => eventHover(event, copy)),
    hovertemplate: '%{text}<extra></extra>',
    marker: { size: 14, symbol, color: fill, line: { color: outline, width: 2 } },
  }
}

const TransitionTimeline = memo(function TransitionTimeline({ transitions, plotTheme, copy }) {
  const laneLabels = useMemo(
    () => Array.from({ length: LANE_COUNT }, (_, i) => `${copy.live.light} ${i + 1}`),
    [copy.live.light],
  )

  const data = useMemo(() => {
    const toWhite = transitions.filter((event) => event.to_state === 'white')
    const toRed = transitions.filter((event) => event.to_state !== 'white')
    return [
      directionTrace(
        toWhite,
        { symbol: 'triangle-up', fill: plotlyPalette.white, outline: plotlyPalette.red, name: copy.insights.dirToWhite },
        copy,
      ),
      directionTrace(
        toRed,
        { symbol: 'triangle-down', fill: plotlyPalette.red, outline: plotlyPalette.warn, name: copy.insights.dirToRed },
        copy,
      ),
    ]
  }, [transitions, copy])

  const frames = transitions.map((event) => event.frame_index).filter(Number.isFinite)
  const minFrame = frames.length ? Math.min(...frames) : 0
  const maxFrame = frames.length ? Math.max(...frames) : 1
  const pad = Math.max(1, Math.round((maxFrame - minFrame || 1) * 0.08))

  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={data}
      copy={copy}
      ariaLabel={copy.insights.transitionTimelineTitle}
      layout={basePlotLayout(plotTheme, {
        height: CHART_HEIGHT,
        margin: { l: 78, r: 16, t: 10, b: 56 },
        // Legend below the plot keys the two direction symbols (audit B4).
        legend: { orientation: 'h', x: 0.5, y: -0.16, xanchor: 'center', font: { color: plotTheme.muted, size: 11 } },
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.thFrame, plotTheme),
          range: [minFrame - pad, maxFrame + pad],
          gridcolor: plotTheme.grid,
          zeroline: false,
        }),
        yaxis: baseAxisStyle(plotTheme, {
          // Plotly's y-axis is bottom-up: reverse so the lanes read Light 1 (top) →
          // Light 4 (bottom), matching the table and the app's "Light 1 first" order.
          categoryorder: 'array',
          categoryarray: [...laneLabels].reverse(),
          gridcolor: plotTheme.grid,
        }),
        showlegend: true,
      })}
      useResizeHandler
    />
  )
})

const TransitionCountBar = memo(function TransitionCountBar({ transitions, plotTheme, copy }) {
  const { lamps, counts } = useMemo(() => transitionCountSeries(transitions), [transitions])
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      copy={copy}
      ariaLabel={copy.insights.transitionCountTitle}
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
        height: CHART_HEIGHT,
        margin: { l: 48, r: 16, t: 10, b: 40 },
        xaxis: baseAxisStyle(plotTheme),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.transitionCountAxis, plotTheme),
          gridcolor: plotTheme.grid,
          // Readable integer ticks at any scale (audit B8).
          ...integerTicks(Math.max(0, ...counts)),
          rangemode: 'tozero',
        }),
      })}
      useResizeHandler
    />
  )
})

function TransitionTable({ transitions, copy }) {
  return (
    <div className="transition-table-wrap">
      <table className="transition-table" aria-labelledby="transition-table-heading">
        <thead>
          <tr>
            <th>{copy.insights.thLight}</th>
            <th className="num">{copy.insights.thFrame}</th>
            <th>{copy.insights.thFrom}</th>
            <th>{copy.insights.thTransition}</th>
            <th>{copy.insights.thTo}</th>
            <th className="num">{copy.insights.thAngle}</th>
            <th className="num">{copy.insights.thDuration}</th>
          </tr>
        </thead>
        <tbody>
          {transitions.map((event, index) => {
            const isModel = event.method === 'model'
            return (
              <tr key={`${event.lamp_index}-${event.frame_index}-${index}`}>
                <td>
                  {copy.live.light} {event.lamp_index}
                </td>
                <td className="num mono tnum">{event.frame_index}</td>
                <td>
                  <span className={`state-pill is-${event.from_state}`}>
                    {copy.status?.[event.from_state] ?? event.from_state}
                  </span>
                </td>
                <td>
                  {/* The intermediate state: a model event is an explicit transition-state
                      run, a tracking flip is instantaneous (no intermediate) -> "—". */}
                  {isModel ? (
                    <span className="state-pill is-transition">{copy.status?.transition ?? 'transition'}</span>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <span className={`state-pill is-${event.to_state}`}>
                    {copy.status?.[event.to_state] ?? event.to_state}
                  </span>
                </td>
                <td className="num mono tnum">
                  {Number.isFinite(event.elevation_angle_deg) ? event.elevation_angle_deg.toFixed(3) : '—'}
                </td>
                <td className="num mono tnum">
                  {Number.isFinite(event.duration_frames) ? event.duration_frames : '—'}
                </td>
              </tr>
            )
          })}
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
        // Single source of truth for lamp identity: drop events outside 1..4 here so the
        // timeline, count bar, and table all operate on the same validated set.
        if (Number.isInteger(event?.lamp_index) && event.lamp_index >= 1 && event.lamp_index <= LANE_COUNT) {
          all.push(event)
        }
      }
    }
    return all
  }, [backendResults])

  const provenance = useMemo(() => (transitions.length ? methodLabel(transitions, copy) : ''), [transitions, copy])

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
          {provenance ? <span className="client-tag method-tag">{provenance}</span> : null}
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
