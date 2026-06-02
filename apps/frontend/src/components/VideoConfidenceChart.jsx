import { useMemo } from 'react'
import { Activity } from 'lucide-react'
import { LazyPlot } from './insights/LazyPlot'
import { plotlyConfig } from '../catalog/plotly'
import { backendStateId, stateCatalog } from '../catalog/stateCatalog'
import { translateState } from '../i18n/translate'

// Map a backend global_state ("correct_glidepath", ...) to its localized label,
// mirroring the Insights panels so the chart hover reads the same as the rest of
// the app (the per-frame `state` is a backend GlobalState, not a frontend id).
function stateLabel(rawState, copy) {
  const id = backendStateId[rawState] ?? 'unknown'
  const entry = stateCatalog.find((state) => state.id === id)
  return entry ? translateState(entry, copy).label : rawState
}

// Frame-by-frame detection confidence for a video / folder-sequence analysis.
// `perFrame` is the backend's raw per-frame series [{ frame_index, confidence, state }];
// we plot confidence (%) over frame index with the per-frame verdict in the hover.
export function VideoConfidenceChart({ perFrame, plotTheme, copy }) {
  const data = useMemo(() => {
    const points = perFrame ?? []
    return [
      {
        type: 'scatter',
        mode: 'lines+markers',
        x: points.map((point) => point.frame_index),
        y: points.map((point) => Math.round(point.confidence * 100)),
        customdata: points.map((point) => stateLabel(point.state, copy)),
        line: { color: plotTheme.accent, width: 2 },
        marker: { size: 6, color: plotTheme.accent },
        fill: 'tozeroy',
        fillcolor: plotTheme.accentSoft,
        hovertemplate:
          `${copy.live.frameAxis}: %{x}<br>` +
          `${copy.live.frameConfidenceAxis}: %{y}%<br>` +
          `%{customdata}<extra></extra>`,
      },
    ]
  }, [perFrame, plotTheme, copy])

  const layout = {
    autosize: true,
    height: 280,
    margin: { l: 52, r: 16, t: 10, b: 44 },
    paper_bgcolor: plotTheme.paper,
    plot_bgcolor: plotTheme.paper,
    font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
    xaxis: {
      title: { text: copy.live.frameAxis, font: { color: plotTheme.muted, size: 11 } },
      gridcolor: plotTheme.grid,
      zeroline: false,
      fixedrange: true,
      tickfont: { color: plotTheme.muted },
    },
    yaxis: {
      title: { text: copy.live.frameConfidenceAxis, font: { color: plotTheme.muted, size: 11 } },
      range: [0, 100],
      gridcolor: plotTheme.grid,
      fixedrange: true,
      tickfont: { color: plotTheme.muted },
    },
    showlegend: false,
  }

  return (
    <article className="viz-card video-confidence-card">
      <div className="viz-heading">
        <Activity size={18} />
        <div>
          <h3>{copy.live.frameConfidenceTitle}</h3>
          <p>{copy.live.frameConfidenceText}</p>
        </div>
      </div>
      <LazyPlot className="plotly-chart" config={plotlyConfig} data={data} layout={layout} useResizeHandler />
    </article>
  )
}
