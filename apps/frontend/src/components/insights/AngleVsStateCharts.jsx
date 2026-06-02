import { useMemo } from 'react'
import { Compass } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { plotlyConfig, plotlyPalette } from '../../catalog/plotly'
import { angleVsStateSeries } from '../../lib/insightsTransforms'

// THE client-critical chart: elevation angle (from image GPS EXIF) versus each
// light's classified state, one chart per light. The angle is real backend data
// (apps/backend angle.py computes it from GPS + lamp WGS84 coords); we never
// fabricate it. With no geotagged imagery the honest empty-state is shown.
// The angleVsStateSeries transform lives in lib/insightsTransforms.js.

const STATE_COLOR = {
  obscured: '#7b8794',
  red: plotlyPalette.red,
  transition: plotlyPalette.transition,
  white: plotlyPalette.white,
}

function AngleChart({ lampIndex, points, plotTheme, copy }) {
  if (!points.length) {
    return (
      <div className="angle-chart angle-chart--empty">
        <h4>
          {copy.live.light} {lampIndex}
        </h4>
        <p>{copy.insights.angleLightNoData}</p>
      </div>
    )
  }

  const data = [
    {
      type: 'scatter',
      mode: points.length > 1 ? 'lines+markers' : 'markers',
      x: points.map((point) => point.angle),
      y: points.map((point) => point.stateNum),
      line: { color: plotTheme.accentSoft, shape: 'hv', width: 1 },
      marker: {
        size: 11,
        color: points.map((point) => STATE_COLOR[point.state]),
        line: { color: plotTheme.strong, width: 1.4 },
      },
      customdata: points.map((point) => [
        point.label,
        point.confidence,
        copy.status?.[point.state] ?? point.state,
      ]),
      hovertemplate:
        `${copy.insights.angleSource}: %{customdata[0]}<br>` +
        `${copy.insights.angleAxis}: %{x:.3f}<br>` +
        `${copy.insights.stateAxis}: %{customdata[2]}<br>` +
        `${copy.insights.angleConfidence}: %{customdata[1]}%<extra></extra>`,
    },
  ]

  const layout = {
    autosize: true,
    height: 280,
    margin: { l: 88, r: 14, t: 8, b: 42 },
    paper_bgcolor: plotTheme.paper,
    plot_bgcolor: plotTheme.paper,
    font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
    xaxis: {
      title: { text: copy.insights.angleAxis, font: { color: plotTheme.muted, size: 11 } },
      gridcolor: plotTheme.grid,
      zeroline: false,
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
    showlegend: false,
  }

  return (
    <div className="angle-chart">
      <h4>
        {copy.live.light} {lampIndex}
      </h4>
      <LazyPlot
        className="plotly-chart"
        config={plotlyConfig}
        data={data}
        layout={layout}
        useResizeHandler
      />
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
        <div className="angle-grid">
          {series.map((lamp) => (
            <AngleChart
              key={lamp.lampIndex}
              lampIndex={lamp.lampIndex}
              points={lamp.points}
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
