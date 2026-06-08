import { memo, useMemo } from 'react'
import { Compass, TrendingDown } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import {
  axisTitle,
  basePlotLayout,
  baseAxisStyle,
  plotlyConfig,
  CHART_HEIGHT,
  LAMP_COLORS,
  SEQUENCE_COLORS,
} from '../../catalog/plotly'
import { angleVsStateSeries, elevationOverFrameSeries } from '../../lib/insightsTransforms'

// THE client-critical chart: each PAPI lamp's classified STATE (red→transition→white)
// against the real elevation angle, all four lamps on ONE shared angle ruler. The
// vertical riser in each lamp's step line sits at the angle where it flipped red↔white
// — the commissioning event — so the engineer reads each lamp's transition angle and
// their ordering directly, instead of four flat confidence ribbons (readability audit
// P0-A). Lamp identity = CVD-safe LAMP_COLORS, kept distinct from the red/white state
// colours used elsewhere.

// Ordinal state axis: obscured sits below red so non-detections are still visible.
const STATE_TICKVALS = [-1, 0, 1, 2]
// Small per-lamp Y offset so four lamps sharing a state (e.g. all white) don't draw on
// top of each other — colour still identifies the lamp; the offset only de-occludes.
const stateOffset = (lampIndex) => (lampIndex - 1) * 0.05

function lampName(lampIndex, copy) {
  return `${copy.live.light} ${lampIndex}`
}

const LightStateChart = memo(function LightStateChart({ series, plotTheme, copy }) {
  const populated = series.filter((lamp) => lamp.points.length > 0)
  const angles = populated.flatMap((lamp) => lamp.points.map((point) => point.angle))
  const minAngle = angles.length ? Math.min(...angles) : 2
  const maxAngle = angles.length ? Math.max(...angles) : 4
  const span = maxAngle - minAngle
  const pad = span > 0 ? span * 0.03 : 0.3

  const stateTicktext = [
    copy.status?.obscured ?? 'obscured',
    copy.status?.red ?? 'red',
    copy.status?.transition ?? 'transition',
    copy.status?.white ?? 'white',
  ]

  const data = populated.map((lamp) => {
    const color = LAMP_COLORS[lamp.lampIndex - 1]
    const offset = stateOffset(lamp.lampIndex)
    const baseName = lampName(lamp.lampIndex, copy)
    // Append the detected crossing angle to the legend so each lamp's transition angle
    // is readable without hovering.
    const name = Number.isFinite(lamp.transitionAngle)
      ? `${baseName} · ${lamp.transitionAngle.toFixed(2)}°`
      : baseName
    return {
      type: 'scatter',
      // Step (horizontal-then-vertical) so the flip reads as a vertical riser whose
      // x-position IS the transition angle. Sparse (single-fix) lamps fall back to a
      // marker so a lone point is still visible.
      mode: lamp.points.length > 3 ? 'lines' : 'markers',
      name,
      x: lamp.points.map((point) => point.angle),
      y: lamp.points.map((point) => point.stateNum + offset),
      line: { color, shape: 'hv', width: 2 },
      marker: { color, size: 7 },
      customdata: lamp.points.map((point) => [copy.status?.[point.state] ?? point.state, point.confidence]),
      hovertemplate:
        `${copy.insights.angleAxis}: %{x:.2f}°<br>` +
        `${copy.insights.stateAxis}: %{customdata[0]}<br>` +
        `${copy.insights.angleConfidence}: %{customdata[1]}%<extra>${name}</extra>`,
    }
  })

  const layout = basePlotLayout(plotTheme, {
    height: 440,
    margin: { l: 104, r: 16, t: 16, b: 56 },
    legend: { orientation: 'h', x: 0.5, y: -0.16, xanchor: 'center', font: { color: plotTheme.muted, size: 11 } },
    xaxis: baseAxisStyle(plotTheme, {
      title: axisTitle(copy.insights.angleAxis, plotTheme),
      range: [minAngle - pad, maxAngle + pad],
      gridcolor: plotTheme.grid,
      zeroline: false,
    }),
    yaxis: baseAxisStyle(plotTheme, {
      title: axisTitle(copy.insights.stateAxis, plotTheme),
      tickvals: STATE_TICKVALS,
      ticktext: stateTicktext,
      range: [-1.4, 2.4],
      gridcolor: plotTheme.grid,
      zeroline: false,
    }),
    showlegend: true,
  })

  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={data}
      layout={layout}
      copy={copy}
      ariaLabel={copy.insights.angleTitle}
      useResizeHandler
    />
  )
})

// Deliverable #3: elevation angle over frame — the real descent profile from each
// analysed video/sequence's telemetry track. One NEUTRAL-coloured line per series, so
// a sequence line is never confused with a "Light N" lamp colour (readability audit).
const ElevationOverFrameChart = memo(function ElevationOverFrameChart({ series, plotTheme, copy }) {
  const multi = series.length > 1
  const data = series.map((entry, index) => ({
    type: 'scatter',
    mode: 'lines',
    name: entry.label,
    x: entry.frames,
    y: entry.angles,
    line: { color: SEQUENCE_COLORS[index % SEQUENCE_COLORS.length], width: 2 },
    hovertemplate:
      `${copy.insights.thFrame}: %{x}<br>${copy.insights.elevationAxis}: %{y:.2f}°<extra>${entry.label}</extra>`,
  }))
  const layout = basePlotLayout(plotTheme, {
    height: CHART_HEIGHT,
    margin: { l: 64, r: 16, t: 10, b: multi ? 64 : 42 },
    showlegend: multi,
    legend: { orientation: 'h', x: 0.5, y: -0.18, xanchor: 'center', font: { color: plotTheme.muted, size: 11 } },
    xaxis: baseAxisStyle(plotTheme, {
      title: axisTitle(copy.insights.thFrame, plotTheme),
      gridcolor: plotTheme.grid,
      zeroline: false,
    }),
    yaxis: baseAxisStyle(plotTheme, {
      title: axisTitle(copy.insights.elevationAxis, plotTheme),
      gridcolor: plotTheme.grid,
    }),
  })
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={data}
      layout={layout}
      copy={copy}
      ariaLabel={copy.insights.elevationTitle}
      useResizeHandler
    />
  )
})

export function AngleVsStateCharts({ backendResults, plotTheme, copy }) {
  const series = useMemo(() => angleVsStateSeries(backendResults), [backendResults])
  const elevationSeries = useMemo(() => elevationOverFrameSeries(backendResults), [backendResults])
  const hasAny = series.some((lamp) => lamp.points.length > 0)

  return (
    <>
      <article className="viz-card angle-card span-all">
        <div className="viz-heading">
          <Compass size={18} />
          <div>
            <h3>{copy.insights.angleTitle}</h3>
            <p>{copy.insights.angleText}</p>
          </div>
          <span className="client-tag">{copy.insights.angleClientTag}</span>
        </div>

        {hasAny ? (
          <LightStateChart series={series} plotTheme={plotTheme} copy={copy} />
        ) : (
          <AngleEmptyState
            icon={<Compass size={26} aria-hidden="true" />}
            title={copy.insights.angleEmptyTitle}
            message={copy.insights.angleEmptyText}
          />
        )}
      </article>

      <article className="viz-card span-all">
        <div className="viz-heading">
          <TrendingDown size={18} />
          <div>
            <h3>{copy.insights.elevationTitle}</h3>
            <p>{copy.insights.elevationText}</p>
          </div>
        </div>
        {elevationSeries.length ? (
          <ElevationOverFrameChart series={elevationSeries} plotTheme={plotTheme} copy={copy} />
        ) : (
          <AngleEmptyState
            icon={<TrendingDown size={26} aria-hidden="true" />}
            message={copy.insights.elevationEmpty}
          />
        )}
      </article>
    </>
  )
}
