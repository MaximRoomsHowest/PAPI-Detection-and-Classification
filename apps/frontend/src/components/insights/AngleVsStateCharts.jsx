import { memo, useMemo } from 'react'
import { Compass, TrendingDown } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { axisTitle, basePlotLayout, baseAxisStyle, plotlyConfig, CHART_HEIGHT, LAMP_COLORS } from '../../catalog/plotly'
import { angleBrightnessSeries, elevationOverFrameSeries } from '../../lib/insightsTransforms'

// Client-critical chart modelled on the AGL Altitude tool: one confidence/visibility
// curve per lamp, plotted against real elevation angle, plus a descent-profile
// (elevation-over-frame) chart. Lamp-IDENTITY colours come from the CVD-safe Okabe-Ito
// palette (catalog/plotly.js) and are deliberately distinct from the red/white/transition
// STATE colours so a series is never misread as a lamp state (audit B3).
const lampColor = (lampIndex) => LAMP_COLORS[lampIndex - 1]
const THRESHOLD_COLOR = '#2e8d46'
const TRANSITION_COLOR = '#b04cc8'

function lampName(lampIndex, copy) {
  return `${copy.live.light} ${lampIndex}`
}

function intersectionLabel(transitionAngle, copy) {
  if (!Number.isFinite(transitionAngle)) {
    return ''
  }
  return `${copy.insights.intersectionLabel}: ${transitionAngle.toFixed(2)}°`
}

const AngleChart = memo(function AngleChart({ lampIndex, points, transitionAngle, threshold, plotTheme, copy }) {
  const name = lampName(lampIndex, copy)
  if (!points.length) {
    return (
      <div className="angle-chart angle-chart--empty">
        <h4>{name}</h4>
        <p>{copy.insights.angleLightNoData}</p>
      </div>
    )
  }

  const color = lampColor(lampIndex)
  const transitionName = copy.insights.transitionAngleName.replace('{lamp}', name)
  const angles = points.map((point) => point.angle)
  const minAngle = Math.min(...angles)
  const maxAngle = Math.max(...angles)
  const axisMin = minAngle === maxAngle ? minAngle - 0.5 : minAngle
  const axisMax = minAngle === maxAngle ? maxAngle + 0.5 : maxAngle

  const data = [
    {
      type: 'scatter',
      // Linear, not spline: the samples are discrete per-frame confidences, so a
      // smoothed curve would imply a continuous function the data doesn't support
      // (and could overshoot) — audit B2.
      mode: 'lines+markers',
      name,
      x: points.map((point) => point.angle),
      y: points.map((point) => point.brightness),
      line: { color, shape: 'linear', width: 2.3 },
      marker: { size: 4, color },
      // [state label, source label] — the confidence value is already the y-axis, so
      // it is no longer duplicated as its own hover row (audit A2).
      customdata: points.map((point) => [copy.status?.[point.state] ?? point.state, point.label || '']),
      hovertemplate:
        `${copy.insights.angleAxis}: %{x:.3f}°<br>` +
        `${copy.insights.brightnessAxis}: %{y:.0f}%<br>` +
        `${copy.insights.stateAxis}: %{customdata[0]}<extra>%{customdata[1]}</extra>`,
    },
    {
      type: 'scatter',
      mode: 'lines',
      name: copy.insights.visibilityThreshold,
      x: [axisMin, axisMax],
      y: [threshold, threshold],
      line: { color: THRESHOLD_COLOR, dash: 'dash', width: 1.4 },
      hovertemplate: `${copy.insights.visibilityThreshold}: %{y:.0f}%<extra></extra>`,
    },
  ]

  if (Number.isFinite(transitionAngle)) {
    data.push({
      type: 'scatter',
      mode: 'lines',
      name: transitionName,
      x: [transitionAngle, transitionAngle],
      y: [0, 100],
      line: { color: TRANSITION_COLOR, dash: 'dash', width: 1.6 },
      hovertemplate: `${transitionName}: %{x:.3f}°<extra></extra>`,
    })
  }

  const layout = basePlotLayout(plotTheme, {
    height: CHART_HEIGHT,
    // Bottom margin leaves room for the horizontal legend below the plot, so the
    // legend no longer overlaps the curve on the right edge (audit: legend overlap).
    margin: { l: 96, r: 14, t: 24, b: 64 },
    legend: {
      orientation: 'h',
      x: 0.5,
      y: -0.18,
      xanchor: 'center',
      yanchor: 'top',
      bgcolor: 'rgba(0,0,0,0)',
      font: { color: plotTheme.muted, size: 11 },
    },
    xaxis: baseAxisStyle(plotTheme, {
      title: axisTitle(copy.insights.angleAxis, plotTheme),
      range: [axisMin, axisMax],
      gridcolor: plotTheme.grid,
      zeroline: false,
    }),
    yaxis: baseAxisStyle(plotTheme, {
      title: axisTitle(copy.insights.brightnessAxis, plotTheme),
      range: [0, 105],
      gridcolor: plotTheme.grid,
    }),
    annotations: Number.isFinite(transitionAngle)
      ? [
          {
            x: transitionAngle,
            y: 100,
            xanchor: 'center',
            yanchor: 'bottom',
            text: intersectionLabel(transitionAngle, copy),
            showarrow: false,
            font: { color: TRANSITION_COLOR, size: 11 },
          },
        ]
      : [],
    showlegend: true,
  })

  return (
    <div className="angle-chart">
      <h4>{name}</h4>
      <LazyPlot
        className="plotly-chart"
        config={plotlyConfig}
        data={data}
        layout={layout}
        copy={copy}
        ariaLabel={`${copy.insights.brightnessAxis} — ${name}`}
        useResizeHandler
      />
    </div>
  )
})

// Deliverable #3: elevation angle over frame — the real descent profile from each
// analysed video/sequence's telemetry track (audit B6). One line per series.
const ElevationOverFrameChart = memo(function ElevationOverFrameChart({ series, plotTheme, copy }) {
  const multi = series.length > 1
  const data = series.map((entry, index) => ({
    type: 'scatter',
    mode: 'lines',
    name: entry.label,
    x: entry.frames,
    y: entry.angles,
    line: { color: LAMP_COLORS[index % LAMP_COLORS.length], width: 2 },
    hovertemplate:
      `${copy.insights.thFrame}: %{x}<br>${copy.insights.elevationAxis}: %{y:.3f}°<extra>${entry.label}</extra>`,
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
  const series = useMemo(() => angleBrightnessSeries(backendResults), [backendResults])
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
          <div className="angle-stack">
            {series.map((lamp) => (
              <AngleChart
                key={lamp.lampIndex}
                lampIndex={lamp.lampIndex}
                points={lamp.points}
                transitionAngle={lamp.transitionAngle}
                threshold={lamp.threshold}
                plotTheme={plotTheme}
                copy={copy}
              />
            ))}
          </div>
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
