import { useMemo } from 'react'
import { BarChart3, SignalHigh } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { axisTitle, basePlotLayout, baseAxisStyle, plotlyConfig, plotlyPalette } from '../../catalog/plotly'
import { confidenceValues, perLightStateSeries } from '../../lib/insightsTransforms'

// Session-level distributions built from the real per-lamp results of the
// current session (lamps[].state / .confidence). These sidestep the /api/stats
// per-light gap entirely by aggregating only what the backend actually returned
// for the media analysed this session — no fabrication. The aggregation
// transforms live in lib/insightsTransforms.js.

const STATES = ['white', 'red', 'transition', 'obscured', 'unknown']
const STATE_COLOR = {
  white: plotlyPalette.white,
  red: plotlyPalette.red,
  transition: plotlyPalette.transition,
  obscured: '#7b8794',
  unknown: '#9aa5b1',
}

function PerLightStateMix({ results, plotTheme, copy }) {
  const counts = useMemo(() => perLightStateSeries(results), [results])
  const lights = [1, 2, 3, 4].map((index) => `${copy.live.light} ${index}`)
  const data = STATES.map((state) => ({
    type: 'bar',
    name: copy.status?.[state] ?? state,
    x: lights,
    y: counts.map((entry) => entry[state]),
    marker: { color: STATE_COLOR[state], line: { color: plotTheme.border, width: 1 } },
    hovertemplate: `%{x}<br>${copy.status?.[state] ?? state}: %{y}<extra></extra>`,
  }))
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={data}
      layout={basePlotLayout(plotTheme, {
        height: 320,
        barmode: 'stack',
        margin: { l: 44, r: 14, t: 10, b: 40 },
        legend: { orientation: 'h', y: -0.18, font: { color: plotTheme.muted, size: 11 } },
        xaxis: baseAxisStyle(plotTheme),
        yaxis: baseAxisStyle(plotTheme, {
          gridcolor: plotTheme.grid,
          dtick: 1,
          rangemode: 'tozero',
        }),
      })}
      useResizeHandler
    />
  )
}

function ConfidenceDistribution({ results, plotTheme, copy }) {
  const values = useMemo(() => confidenceValues(results), [results])
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={[
        {
          type: 'histogram',
          x: values,
          marker: { color: plotTheme.accent, line: { color: plotTheme.paper, width: 1 } },
          xbins: { start: 0, end: 100, size: 10 },
          hovertemplate: `${copy.insights.confidenceAxis}: %{x}<br>%{y}<extra></extra>`,
        },
      ]}
      layout={basePlotLayout(plotTheme, {
        height: 320,
        bargap: 0.04,
        margin: { l: 44, r: 14, t: 10, b: 42 },
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.confidenceAxis, plotTheme),
          range: [0, 100],
          gridcolor: plotTheme.grid,
        }),
        yaxis: baseAxisStyle(plotTheme, {
          gridcolor: plotTheme.grid,
          rangemode: 'tozero',
        }),
      })}
      useResizeHandler
    />
  )
}

export function SessionSummaryCharts({ backendResults, plotTheme, copy }) {
  const hasData = (backendResults?.length ?? 0) > 0
  // The confidence histogram filters to confidence > 0, so a session where every
  // lamp came back unknown/0 would otherwise render an empty-but-populated chart;
  // gate it on its own derived data instead of the shared hasData (audit FB-09).
  const hasConfidenceData = useMemo(
    () => confidenceValues(backendResults).length > 0,
    [backendResults],
  )
  return (
    <>
      <article className="viz-card">
        <div className="viz-heading">
          <BarChart3 size={18} />
          <div>
            <h3>{copy.insights.perLightStateTitle}</h3>
            <p>{copy.insights.perLightStateText}</p>
          </div>
        </div>
        {hasData ? (
          <PerLightStateMix results={backendResults} plotTheme={plotTheme} copy={copy} />
        ) : (
          <AngleEmptyState
            icon={<BarChart3 size={26} aria-hidden="true" />}
            message={copy.insights.noSessionData}
          />
        )}
        <p className="viz-footnote">{copy.insights.perLightGap}</p>
      </article>

      <article className="viz-card">
        <div className="viz-heading">
          <SignalHigh size={18} />
          <div>
            <h3>{copy.insights.confidenceTitle}</h3>
            <p>{copy.insights.confidenceText}</p>
          </div>
        </div>
        {hasConfidenceData ? (
          <ConfidenceDistribution results={backendResults} plotTheme={plotTheme} copy={copy} />
        ) : (
          <AngleEmptyState
            icon={<SignalHigh size={26} aria-hidden="true" />}
            message={copy.insights.noSessionData}
          />
        )}
      </article>
    </>
  )
}
