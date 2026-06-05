import { useMemo } from 'react'
import { Compass } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { axisTitle, basePlotLayout, baseAxisStyle, plotlyConfig } from '../../catalog/plotly'
import { angleBrightnessSeries } from '../../lib/insightsTransforms'

// Client-critical chart modelled on the AGL Altitude tool: one stacked
// brightness/visibility curve per lamp, plotted against real elevation angle.
const lampColor = (lampIndex, plotTheme) =>
  ['#2f6fed', '#e23b3b', '#1f9d57', plotTheme.strong][lampIndex - 1]
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

function AngleChart({ lampIndex, points, transitionAngle, threshold, plotTheme, copy }) {
  const name = lampName(lampIndex, copy)
  if (!points.length) {
    return (
      <div className="angle-chart angle-chart--empty">
        <h4>{name}</h4>
        <p>{copy.insights.angleLightNoData}</p>
      </div>
    )
  }

  const color = lampColor(lampIndex, plotTheme)
  const transitionName = copy.insights.transitionAngleName.replace('{lamp}', name)
  const angles = points.map((point) => point.angle)
  const minAngle = Math.min(...angles)
  const maxAngle = Math.max(...angles)
  const axisMin = minAngle === maxAngle ? minAngle - 0.5 : minAngle
  const axisMax = minAngle === maxAngle ? maxAngle + 0.5 : maxAngle

  const data = [
    {
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: points.map((point) => point.angle),
      y: points.map((point) => point.brightness),
      line: { color, shape: 'spline', smoothing: 0.45, width: 2.3 },
      marker: { size: 4, color },
      customdata: points.map((point) => [
        copy.status?.[point.state] ?? point.state,
        point.confidence,
        point.label || '',
      ]),
      hovertemplate:
        `${copy.insights.angleAxis}: %{x:.3f}<br>` +
        `${copy.insights.brightnessAxis}: %{y:.0f}%<br>` +
        `${copy.insights.stateAxis}: %{customdata[0]}<br>` +
        `${copy.insights.angleConfidence}: %{customdata[1]}%<extra>%{customdata[2]}</extra>`,
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
    height: 210,
    margin: { l: 96, r: 14, t: 8, b: 42 },
    // Legend top-right inside the plot, matching the client tool.
    legend: {
      x: 1,
      y: 1,
      xanchor: 'right',
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
      <LazyPlot className="plotly-chart" config={plotlyConfig} data={data} layout={layout} useResizeHandler />
    </div>
  )
}

export function AngleVsStateCharts({ backendResults, plotTheme, copy }) {
  const series = useMemo(() => angleBrightnessSeries(backendResults), [backendResults])
  const hasAny = series.some((lamp) => lamp.points.length > 0)

  return (
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
  )
}
