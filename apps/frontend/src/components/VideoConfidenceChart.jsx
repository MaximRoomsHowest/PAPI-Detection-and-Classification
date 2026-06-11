import { memo, useMemo } from 'react'
import { Activity } from 'lucide-react'
import { LazyPlot } from './insights/LazyPlot'
import { axisTitle, basePlotLayout, baseAxisStyle, plotlyConfig } from '../catalog/plotly'
import { backendStateId, stateCatalog } from '../catalog/stateCatalog'
import { translateState } from '../i18n/translate'

// Map a backend global_state ("correct_glidepath", ...) to its localized label,
// mirroring the Insights panels so the chart hover reads the same as the rest of
// the app (the per-frame `state` is a backend GlobalState, not a frontend id).
function stateLabel(rawState, copy) {
  const id = backendStateId[rawState]
  if (id) {
    const entry = stateCatalog.find((state) => state.id === id)
    if (entry) return translateState(entry, copy).label
  }
  // Backend global states with no entry in backendStateId / stateCatalog fall back
  // to the localized status label, then a prettified raw value — so an unmapped raw
  // state's hover never silently reads "Unknown".
  return copy.status?.[rawState] ?? rawState.replace(/_/g, ' ')
}

// Frame-by-frame detection confidence for a video / folder-sequence analysis.
// `perFrame` is the backend's raw per-frame series [{ frame_index, confidence, state }];
// we plot confidence (%) over frame index with the per-frame verdict in the hover.
//
// Memoized (export below): during a re-run or telemetry typing the Live-Demo
// context value changes every progress tick, re-rendering the parent while this
// chart's props stay identical — perFrame comes from the memoized activeScenario,
// plotTheme is memoized on theme, copy is a module constant. memo() skips the
// Plotly re-render in that case; keep those three props identity-stable.
function VideoConfidenceChartInner({ perFrame, plotTheme, copy }) {
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

  // Built from the shared catalog helpers (audit REFACTOR-7) so this chart matches every
  // other LazyPlot consumer instead of hand-rolling autosize/bgcolor/font/axis blocks.
  // Memoized so Plotly receives a stable layout object on the re-renders that do
  // happen (e.g. a new perFrame series under the same theme/locale).
  const layout = useMemo(
    () =>
      basePlotLayout(plotTheme, {
        height: 280,
        margin: { l: 52, r: 16, t: 10, b: 44 },
        showlegend: false,
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.live.frameAxis, plotTheme),
          gridcolor: plotTheme.grid,
          zeroline: false,
        }),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.live.frameConfidenceAxis, plotTheme),
          range: [0, 100],
          gridcolor: plotTheme.grid,
        }),
      }),
    [plotTheme, copy],
  )

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

export const VideoConfidenceChart = memo(VideoConfidenceChartInner)
