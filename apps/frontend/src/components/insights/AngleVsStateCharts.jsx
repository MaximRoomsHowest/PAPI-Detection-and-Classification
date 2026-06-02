import { useMemo } from 'react'
import { Compass } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { plotlyConfig, plotlyPalette } from '../../catalog/plotly'
import { angleVsStateSeries } from '../../lib/insightsTransforms'

// THE client-critical chart (modelled on the client's AGL Altitude tool): for each
// PAPI lamp, the lamp's classified state plotted against the elevation angle (from
// each image's GPS EXIF) across a geotagged descent sequence, with a dashed line at
// the detected red->white transition angle. One stacked chart per lamp (PAPI A-D).
// The angle is real backend data; the state is the model's classification; the
// transition angle is derived from the real samples (lib/insightsTransforms.js).
// Nothing is fabricated — with no geotagged sweep the honest empty-state shows.

const LAMP_LETTERS = ['A', 'B', 'C', 'D']
// Per-lamp line colours (theme-agnostic, readable in light + dark). PAPI D uses the
// theme's strong colour so it reads dark on light / light on dark, like the client tool.
const lampColor = (lampIndex, plotTheme) =>
  ['#2f6fed', '#e23b3b', '#1f9d57', plotTheme.strong][lampIndex - 1]
// Consistent dashed transition-angle marker colour across all four charts.
const TRANSITION_COLOR = plotlyPalette.red

function lampName(lampIndex) {
  return `PAPI ${LAMP_LETTERS[lampIndex - 1] ?? lampIndex}`
}

function AngleChart({ lampIndex, points, transitionAngle, plotTheme, copy }) {
  const name = lampName(lampIndex)
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

  const data = [
    {
      type: 'scatter',
      mode: 'lines+markers',
      name,
      x: points.map((point) => point.angle),
      y: points.map((point) => point.stateNum),
      line: { color, shape: 'hv', width: 2 },
      marker: { size: 6, color },
      customdata: points.map((point) => [
        copy.status?.[point.state] ?? point.state,
        point.confidence,
        point.label || '',
      ]),
      hovertemplate:
        `${copy.insights.angleAxis}: %{x:.3f}<br>` +
        `${copy.insights.stateAxis}: %{customdata[0]}<br>` +
        `${copy.insights.angleConfidence}: %{customdata[1]}%<extra>%{customdata[2]}</extra>`,
    },
  ]

  if (Number.isFinite(transitionAngle)) {
    data.push({
      type: 'scatter',
      mode: 'lines',
      name: transitionName,
      x: [transitionAngle, transitionAngle],
      y: [-1.4, 2.4],
      line: { color: TRANSITION_COLOR, dash: 'dash', width: 1.6 },
      hovertemplate: `${transitionName}: %{x:.3f}°<extra></extra>`,
    })
  }

  const layout = {
    autosize: true,
    height: 210,
    margin: { l: 96, r: 14, t: 8, b: 42 },
    paper_bgcolor: plotTheme.paper,
    plot_bgcolor: plotTheme.paper,
    font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
    // Legend top-right inside the plot, matching the client tool.
    legend: {
      x: 1,
      y: 1,
      xanchor: 'right',
      yanchor: 'top',
      bgcolor: 'rgba(0,0,0,0)',
      font: { color: plotTheme.muted, size: 11 },
    },
    xaxis: {
      title: { text: copy.insights.angleAxis, font: { color: plotTheme.muted, size: 11 } },
      gridcolor: plotTheme.grid,
      zeroline: false,
      fixedrange: true,
      tickfont: { color: plotTheme.muted },
    },
    yaxis: {
      tickvals: [-1, 0, 1, 2],
      ticktext: [copy.status.obscured, copy.status.red, copy.status.transition, copy.status.white],
      range: [-1.4, 2.4],
      fixedrange: true,
      gridcolor: plotTheme.grid,
      tickfont: { color: plotTheme.muted },
    },
    showlegend: true,
  }

  return (
    <div className="angle-chart">
      <h4>{name}</h4>
      <LazyPlot className="plotly-chart" config={plotlyConfig} data={data} layout={layout} useResizeHandler />
    </div>
  )
}

export function AngleVsStateCharts({ backendResults, plotTheme, copy }) {
  const series = useMemo(() => angleVsStateSeries(backendResults), [backendResults])
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
