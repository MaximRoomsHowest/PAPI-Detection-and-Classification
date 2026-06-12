import { memo, useMemo } from 'react'
import { Activity } from 'lucide-react'
import { LazyPlot } from './insights/LazyPlot'
import { axisTitle, basePlotLayout, baseAxisStyle, plotlyConfig } from '../catalog/plotly'
import { globalStateLabel } from '../lib/stateLabels'

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
        customdata: points.map((point) => globalStateLabel(point.state, copy)),
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
      {/* copy + ariaLabel: localized loading/error fallbacks and a screen-reader
          name for the SVG chart — this was the only LazyPlot call site without
          them (every Insights chart already passes both). */}
      <LazyPlot
        className="plotly-chart"
        copy={copy}
        ariaLabel={copy.live.frameConfidenceTitle}
        config={plotlyConfig}
        data={data}
        layout={layout}
        useResizeHandler
      />
    </article>
  )
}

export const VideoConfidenceChart = memo(VideoConfidenceChartInner)
