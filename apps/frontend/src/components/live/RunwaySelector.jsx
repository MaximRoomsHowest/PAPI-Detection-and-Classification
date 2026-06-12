import { Link } from 'react-router-dom'
import { MapPin, RefreshCw, Settings2 } from 'lucide-react'
import { useLiveDemo } from '../../context/liveDemoContext'
import { runwayDisplayName } from '../../lib/runwaySelection'

function errorMessage(error) {
  return error?.message || String(error || '')
}

export function RunwaySelector({ copy }) {
  const {
    runways,
    selectedRunwayId,
    selectedRunway,
    setSelectedRunwayId,
    runwayLoading,
    runwayError,
    refetchRunways,
  } = useLiveDemo()
  const selectedLabel = selectedRunway?.label ?? runwayDisplayName(selectedRunwayId, runways)
  const canChoose = runways.length > 0 && !(runwayLoading && runways.length === 0)

  return (
    <div className="live-runway-panel" role="region" aria-labelledby="live-runway-title">
      <div className="live-runway-panel__copy">
        <MapPin size={18} aria-hidden="true" />
        <div>
          <h3 id="live-runway-title">{copy.live.runwaySelectorTitle}</h3>
          <p>{copy.live.runwaySelectorHint}</p>
        </div>
      </div>

      <div className="live-runway-panel__controls">
        <label className="runway-select">
          <span>{copy.live.runway}</span>
          <select
            value={selectedRunwayId}
            onChange={(event) => setSelectedRunwayId(event.target.value)}
            disabled={!canChoose}
            aria-label={copy.live.runway}
            title={!canChoose ? copy.live.runwaySelectDisabled : copy.live.runway}
          >
            {runways.length === 0 && <option value={selectedRunwayId}>{selectedLabel}</option>}
            {runways.map((runway) => (
              <option key={runway.id} value={runway.id}>
                {runway.label ?? runway.id}
              </option>
            ))}
          </select>
        </label>

        <Link className="secondary-button live-runway-panel__manage" to="/runways">
          <Settings2 size={16} aria-hidden="true" />
          {copy.live.manageRunways}
        </Link>
      </div>

      {(runwayLoading || runwayError) && (
        <div
          className={`live-runway-panel__status${runwayError ? ' error' : ''}`}
          role={runwayError ? 'alert' : 'status'}
          aria-live={runwayError ? 'assertive' : 'polite'}
        >
          <span>
            {runwayError
              ? copy.live.runwayLoadError.replace('{message}', errorMessage(runwayError))
              : copy.live.runwayLoading}
          </span>
          {runwayError && (
            <button type="button" className="ghost-button" onClick={refetchRunways}>
              <RefreshCw size={15} aria-hidden="true" />
              {copy.live.runwayRetry}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
