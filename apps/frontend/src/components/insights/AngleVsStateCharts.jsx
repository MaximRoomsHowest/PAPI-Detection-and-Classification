import { memo, useMemo } from 'react'
import { Compass, TrendingDown } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import {
  axisTitle,
  basePlotLayout,
  baseAxisStyle,
  plotlyConfig,
  plotlyPalette,
  CHART_HEIGHT,
  LAMP_COLORS,
  SEQUENCE_COLORS,
} from '../../catalog/plotly'
import { angleVsStateSeries, elevationOverFrameSeries, transitionAngleSummary } from '../../lib/insightsTransforms'

// THE client-critical chart, matching the Intersoft "AGL Altitude" tool's "Redness vs
// angle" view: ONE graph per lamp, Y = measured red-channel REDNESS (high while the lamp
// is red, dropping sharply to a low plateau once it turns white), X = real elevation
// angle, with a dashed vertical line at the lamp's detected red->white transition angle.
// Redness is a real pixel measurement from the backend (lamp.redness), not the
// classified state. Lamp identity uses the CVD-safe LAMP_COLORS; the detected
// crossing marker uses the canonical amber transition token (plotlyPalette.transition)
// so it agrees with the state pills, cards, and the transition zone tint below —
// never a competing off-palette hue (design audit 2026-06-13).
const REDNESS_CHART_HEIGHT = 260

function lampName(lampIndex, copy) {
  return `${copy.live.light} ${lampIndex}`
}

// Contiguous same-state runs over the angle-sorted points -> background rects.
// The redness amplitude can be subtle on day footage, so the classified-state
// context is painted BEHIND the line: red runs tinted red, the blend zone amber.
function stateRunShapes(points, axisMin, axisMax) {
  const tints = {
    red: 'rgba(255, 69, 69, 0.08)',
    transition: 'rgba(255, 177, 31, 0.12)',
  }
  const shapes = []
  let run = null
  const flush = (endAngle) => {
    if (run && tints[run.state]) {
      shapes.push({
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: run.start,
        x1: endAngle,
        y0: 0,
        y1: 1,
        fillcolor: tints[run.state],
        line: { width: 0 },
        layer: 'below',
      })
    }
  }
  for (const point of points) {
    if (!run) {
      run = { state: point.state, start: axisMin }
      continue
    }
    if (point.state !== run.state) {
      // Hand over halfway between the last point of the old run and this one.
      const boundary = (run.lastAngle + point.angle) / 2
      flush(boundary)
      run = { state: point.state, start: boundary }
    }
    run.lastAngle = point.angle
  }
  if (run) {
    flush(axisMax)
  }
  return shapes
}

const RednessChart = memo(function RednessChart({ lampIndex, points, transitionAngle, plotTheme, copy }) {
  const name = lampName(lampIndex, copy)
  const reddable = points.filter((point) => Number.isFinite(point.redness))
  if (!reddable.length) {
    return (
      <div className="angle-chart angle-chart--empty">
        <h4>{name}</h4>
        <p>{copy.insights.angleLightNoData}</p>
      </div>
    )
  }
  const color = LAMP_COLORS[lampIndex - 1]
  const transitionName = copy.insights.transitionAngleName.replace('{lamp}', name)
  const angles = reddable.map((point) => point.angle)
  const minAngle = Math.min(...angles)
  const maxAngle = Math.max(...angles)
  const axisMin = minAngle === maxAngle ? minAngle - 0.5 : minAngle
  const axisMax = minAngle === maxAngle ? maxAngle + 0.5 : maxAngle
  const rednessValues = reddable.map((point) => point.redness)
  const rMin = Math.min(...rednessValues)
  const rMax = Math.max(...rednessValues)

  const data = [
    {
      type: 'scatter',
      // Markers up to a real sweep's length keep individual frames honest;
      // beyond that the line alone reads better.
      mode: reddable.length > 3 && reddable.length <= 80 ? 'lines+markers' : reddable.length > 80 ? 'lines' : 'lines+markers',
      name,
      x: reddable.map((point) => point.angle),
      y: reddable.map((point) => point.redness),
      line: { color, width: 2 },
      marker: { color, size: 3 },
      customdata: reddable.map((point) => copy.status?.[point.state] ?? point.state),
      hovertemplate:
        `${copy.insights.angleAxis}: %{x:.2f}°<br>` +
        `${copy.insights.rednessAxis}: %{y:.0f}<br>` +
        `${copy.insights.stateAxis}: %{customdata}<extra>${name}</extra>`,
    },
  ]
  if (Number.isFinite(transitionAngle)) {
    // Span the data's redness range so the dashed marker is a visible full-height line
    // without expanding the y-axis, and shows in the legend like the client tool.
    data.push({
      type: 'scatter',
      mode: 'lines',
      name: transitionName,
      x: [transitionAngle, transitionAngle],
      y: [rMin, rMax],
      line: { color: plotlyPalette.transition, dash: 'dash', width: 1.6 },
      hovertemplate: `${transitionName}: %{x:.2f}°<extra></extra>`,
    })
  }

  const layout = basePlotLayout(plotTheme, {
    height: REDNESS_CHART_HEIGHT,
    margin: { l: 64, r: 12, t: 8, b: 38 },
    // Legend top-right inside the plot (over the post-drop low plateau), matching the
    // client tool's "PAPI X / PAPI X transition angle" key.
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
      title: axisTitle(copy.insights.rednessAxis, plotTheme),
      gridcolor: plotTheme.grid,
    }),
    // Classified-state context painted behind the redness line.
    shapes: stateRunShapes(reddable, axisMin, axisMax),
    // The detected crossing, labelled with its value right on the line.
    annotations: Number.isFinite(transitionAngle)
      ? [
          {
            xref: 'x',
            yref: 'paper',
            x: transitionAngle,
            y: 1.02,
            text: `${transitionAngle.toFixed(2)}°`,
            showarrow: false,
            font: { color: plotlyPalette.transition, size: 11 },
            xanchor: 'left',
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
        ariaLabel={`${copy.insights.rednessAxis} — ${name}`}
        useResizeHandler
      />
    </div>
  )
})

// Deliverable: elevation angle over frame — the descent profile from each analysed
// sequence's telemetry track. Neutral SEQUENCE_COLORS so a flight line is never the
// same colour as a "Light N" lamp identity in the chart above.
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
  const transitionSummary = useMemo(() => transitionAngleSummary(backendResults), [backendResults])
  const elevationSeries = useMemo(() => elevationOverFrameSeries(backendResults), [backendResults])
  const hasRedness = series.some((lamp) => lamp.points.some((point) => Number.isFinite(point.redness)))

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

        {hasRedness ? (
          <div className="angle-stack">
            {series.map((lamp) => (
              <RednessChart
                key={lamp.lampIndex}
                lampIndex={lamp.lampIndex}
                points={lamp.points}
                transitionAngle={transitionSummary[lamp.lampIndex - 1]?.settledAngle ?? lamp.transitionAngle}
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
