import { useEffect, useState } from 'react'
import { loadPlotlyBundle } from '../../lib/plotlyBundle'

export function LazyPlot(props) {
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
        <strong>Chart unavailable</strong>
        <small>{loadError.message || 'Plotly bundle failed to load.'}</small>
      </div>
    )
  }
  if (!PlotComponent) {
    return <div className="plot-loading" role="status" aria-label="Loading chart" />
  }
  return <PlotComponent {...props} />
}
