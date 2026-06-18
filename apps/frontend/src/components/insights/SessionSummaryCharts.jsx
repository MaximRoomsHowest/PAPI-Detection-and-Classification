import { useMemo } from 'react'
import { BarChart3, SignalHigh } from 'lucide-react'
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
  WHITE_FILL,
  WHITE_OUTLINE,
} from '../../catalog/plotly'
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
  obscured: plotlyPalette.obscured,
  unknown: plotlyPalette.unknown,
}

function PerLightStateMix({ results, plotTheme, copy }) {
  const counts = useMemo(() => perLightStateSeries(results), [results])
  const lights = [1, 2, 3, 4].map((index) => `${copy.live.light} ${index}`)
  const data = STATES.map((state) => ({
    type: 'bar',
    name: copy.status?.[state] ?? state,
    x: lights,
    // Raw counts kept in customdata so the hover stays absolute while the bars are
    // normalised to 100% (so each lamp's red/white split is comparable — audit P0-B).
    y: counts.map((entry) => entry[state]),
    customdata: counts.map((entry) => entry[state]),
    // The near-white "white" state needs a visible outline + faint fill so it doesn't
    // vanish into the card; the rest keep the subtle border (audit P0-B).
    marker:
      state === 'white'
        ? { color: WHITE_FILL, line: { color: WHITE_OUTLINE, width: 1.5 } }
        : { color: STATE_COLOR[state], line: { color: plotTheme.border, width: 1 } },
    hovertemplate: `%{x}<br>${copy.status?.[state] ?? state}: %{customdata}<extra></extra>`,
  }))
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={data}
      copy={copy}
      ariaLabel={copy.insights.perLightStateTitle}
      layout={basePlotLayout(plotTheme, {
        height: CHART_HEIGHT,
        barmode: 'stack',
        barnorm: 'percent',
        margin: { l: 48, r: 14, t: 10, b: 40 },
        legend: { orientation: 'h', y: -0.18, font: { color: plotTheme.muted, size: 11 } },
        xaxis: baseAxisStyle(plotTheme),
        yaxis: baseAxisStyle(plotTheme, {
          gridcolor: plotTheme.grid,
          // 100%-normalised: every lamp's bar is full height so the red/white SHARE is
          // directly comparable across lamps (audit P0-B).
          range: [0, 100],
          ticksuffix: '%',
          dtick: 25,
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
      copy={copy}
      ariaLabel={copy.insights.confidenceTitle}
      data={[
        {
          type: 'histogram',
          x: values,
          marker: { color: plotTheme.accent, line: { color: plotTheme.paper, width: 1 } },
          // end slightly past 100 so a perfect 100%-confidence detection (a half-open
          // bin edge) is still counted in the top bin (audit B7).
          xbins: { start: 0, end: 100.001, size: 10 },
          hovertemplate: `${copy.insights.confidenceAxis}: %{x}<br>${copy.insights.countAxis}: %{y}<extra></extra>`,
        },
      ]}
      layout={basePlotLayout(plotTheme, {
        height: CHART_HEIGHT,
        bargap: 0.04,
        margin: { l: 44, r: 14, t: 10, b: 42 },
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.confidenceAxis, plotTheme),
          range: [0, 100],
          gridcolor: plotTheme.grid,
        }),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.countAxis, plotTheme),
          gridcolor: plotTheme.grid,
          // Detections is an integer count too — keep its ticks whole at low counts (audit B8).
          ...integerTicks(values.length),
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
