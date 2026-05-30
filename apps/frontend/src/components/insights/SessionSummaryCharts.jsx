import { useMemo } from 'react'
import { BarChart3, SignalHigh } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { plotlyConfig, plotlyPalette } from '../../catalog/plotly'
import { confidenceValues, perLightStateSeries } from '../../lib/insightsTransforms'

// Session-level distributions built from the real per-lamp results of the
// current session (lamps[].state / .confidence). These sidestep the /api/stats
// per-light gap entirely by aggregating only what the backend actually returned
// for the media analysed this session — no fabrication. The aggregation
// transforms live in lib/insightsTransforms.js.

const STATES = ['white', 'red', 'transition', 'unknown']
const STATE_COLOR = {
  white: plotlyPalette.white,
  red: plotlyPalette.red,
  transition: plotlyPalette.transition,
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
      layout={{
        autosize: true,
        height: 260,
        barmode: 'stack',
        margin: { l: 44, r: 14, t: 10, b: 40 },
        paper_bgcolor: plotTheme.paper,
        plot_bgcolor: plotTheme.paper,
        font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
        legend: { orientation: 'h', y: -0.18, font: { color: plotTheme.muted, size: 11 } },
        xaxis: { fixedrange: true, tickfont: { color: plotTheme.muted } },
        yaxis: {
          gridcolor: plotTheme.grid,
          fixedrange: true,
          dtick: 1,
          rangemode: 'tozero',
          tickfont: { color: plotTheme.muted },
        },
      }}
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
      layout={{
        autosize: true,
        height: 260,
        bargap: 0.04,
        margin: { l: 44, r: 14, t: 10, b: 42 },
        paper_bgcolor: plotTheme.paper,
        plot_bgcolor: plotTheme.paper,
        font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
        xaxis: {
          title: { text: copy.insights.confidenceAxis, font: { color: plotTheme.muted, size: 11 } },
          range: [0, 100],
          fixedrange: true,
          gridcolor: plotTheme.grid,
          tickfont: { color: plotTheme.muted },
        },
        yaxis: {
          gridcolor: plotTheme.grid,
          fixedrange: true,
          rangemode: 'tozero',
          tickfont: { color: plotTheme.muted },
        },
      }}
      useResizeHandler
    />
  )
}

export function SessionSummaryCharts({ backendResults, plotTheme, copy }) {
  const hasData = (backendResults?.length ?? 0) > 0
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
        {hasData ? (
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
