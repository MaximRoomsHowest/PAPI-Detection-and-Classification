import { useEffect, useState } from 'react'
import { loadPlotlyBundle } from '../../lib/plotlyBundle'

// `copy` (localized loading/error strings) and `ariaLabel` (a screen-reader text
// alternative for the otherwise-silent SVG chart — audit E1/E2) are consumed here
// and NOT forwarded to the underlying Plot.
export function LazyPlot({ copy, ariaLabel, ...props }) {
  const [PlotComponent, setPlotComponent] = useState(null)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    let isMounted = true
    loadPlotlyBundle()
      .then(({ Plot }) => {
        if (isMounted) {
          setPlotComponent(() => Plot)
        }
      })
      .catch((error) => {
        // Surface the failure instead of swallowing it (audit SMOKE-CRIT-3).
        // A blank chart with no console error is undebuggable on stage.
        console.error('Failed to load Plotly bundle:', error)
        if (isMounted) {
          setLoadError(error)
        }
      })
    return () => {
      isMounted = false
    }
  }, [])

  if (loadError) {
    return (
      <div className="plot-loading plot-error" role="alert">
        <strong>{copy?.insights?.chartUnavailable ?? 'Chart unavailable'}</strong>
        <small>{loadError.message || 'Plotly bundle failed to load.'}</small>
      </div>
    )
  }
  if (!PlotComponent) {
    return (
      <div className="plot-loading" role="status" aria-label={copy?.insights?.chartLoading ?? 'Loading chart'} />
    )
  }
  // role="img" + aria-label gives screen readers a name for the SVG chart. The
  // Plotly node (.js-plotly-plot) stays a descendant so the PDF export selector
  // still finds it. Without an ariaLabel we render the Plot bare (unchanged).
  if (ariaLabel) {
    return (
      <div className="plotly-chart-frame" role="img" aria-label={ariaLabel}>
        <PlotComponent {...props} />
      </div>
    )
  }
  return <PlotComponent {...props} />
}
