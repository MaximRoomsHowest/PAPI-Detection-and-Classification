import { MapPin, Upload, X } from 'lucide-react'
import { useLiveDemo } from '../../context/liveDemoContext'
import { FOLDER_MODE_ANGLE_SWEEP } from '../../lib/analysisMode'

// The "angle metadata missing" panel: runway select + telemetry-file upload + manual
// lat/lon/alt fields + the re-run button. Shown only after a result whose angle came
// back unavailable, so the user can supply a fix and re-analyse. Pulls its state and
// handlers from the Live-Demo context; renders nothing when the angle is available.
export function MetadataPrompt({ copy }) {
  const {
    activeScenario,
    backendScenario,
    media,
    runways,
    selectedRunwayId,
    setSelectedRunwayId: onSelectRunway,
    droneTelemetry,
    setDroneTelemetry,
    metadataFile,
    setMetadataFile,
    folderMode,
    runBackendInference,
    isAnalyzing,
  } = useLiveDemo()

  const hasResult = Boolean(backendScenario)
  const hasMissingAngleMetadata = hasResult && !activeScenario.angleSummary?.available
  if (!hasMissingAngleMetadata) return null

  const setDroneField = (field) => (event) =>
    setDroneTelemetry((current) => ({ ...current, [field]: event.target.value }))

  const handleMetadataFileChange = (event) => {
    setMetadataFile(event.target.files?.[0] ?? null)
    // Reset the input so re-selecting the same file still fires onChange.
    event.target.value = ''
  }

  const hasManualDroneTelemetry = Boolean(
    droneTelemetry.latitude.trim() &&
      droneTelemetry.longitude.trim() &&
      droneTelemetry.altitudeM.trim(),
  )
  // In folder ANGLE-SWEEP mode each image is scored against its OWN EXIF GPS, so an uploaded
  // telemetry FILE is intentionally dropped — don't let it enable Apply (which would re-run
  // without ever resolving the angle, looping this prompt). Manual lat/lon/alt still applies (audit).
  const telemetryFileIgnored = media?.type === 'folder' && folderMode === FOLDER_MODE_ANGLE_SWEEP
  const canApplyMetadata = Boolean(
    media && ((metadataFile && !telemetryFileIgnored) || hasManualDroneTelemetry),
  )

  return (
    <div className="metadata-prompt" role="region" aria-labelledby="metadata-prompt-title">
      <div className="metadata-prompt__copy">
        <MapPin size={18} aria-hidden="true" />
        <div>
          <h3 id="metadata-prompt-title">{copy.live.metadataMissingTitle}</h3>
          <p>{copy.live.metadataMissingText}</p>
        </div>
      </div>

      <div className="metadata-prompt__controls">
        <label className="runway-select" htmlFor="metadata-runway-select">
          <span>{copy.live.runway}</span>
          <select
            id="metadata-runway-select"
            name="metadata-runway-select"
            value={selectedRunwayId}
            onChange={(event) => onSelectRunway(event.target.value)}
          >
            {runways.length === 0 && <option value={selectedRunwayId}>{selectedRunwayId}</option>}
            {runways.map((runway) => (
              <option key={runway.id} value={runway.id}>
                {runway.label ?? runway.id}
              </option>
            ))}
          </select>
        </label>

        <div className="drone-telemetry__file-row">
          <label className="upload-button drone-telemetry__file">
            <Upload size={16} />
            <span>{metadataFile ? metadataFile.name : copy.live.telemetryUpload}</span>
            <input
              type="file"
              accept=".srt,.csv,.json,text/plain,text/csv,application/json"
              aria-label={copy.live.telemetryUpload}
              onChange={handleMetadataFileChange}
            />
          </label>
          {metadataFile && (
            <button
              type="button"
              className="drone-telemetry__clear"
              onClick={() => setMetadataFile(null)}
              aria-label={copy.live.telemetryClear}
              title={copy.live.telemetryClear}
            >
              <X size={16} />
            </button>
          )}
          {telemetryFileIgnored && metadataFile && (
            <p className="drone-telemetry__hint" role="status">
              {copy.live.telemetryAngleSweepHint}
            </p>
          )}
        </div>
      </div>

      <span className="drone-telemetry__divider">{copy.live.telemetryOrManual}</span>

      {/* Each field keeps its wrapping <label> (implicit association) and adds an explicit
          id/name plus an aria-describedby range hint, so screen readers announce the accepted
          bounds and the inputs participate in autofill/testing (audit F3). */}
      <div className="drone-telemetry__fields">
        <label htmlFor="drone-latitude">
          <span>{copy.live.droneLatitude}</span>
          <input
            id="drone-latitude"
            name="drone-latitude"
            type="text"
            inputMode="decimal"
            className="mono"
            value={droneTelemetry.latitude}
            onChange={setDroneField('latitude')}
            placeholder="47.673521"
            aria-describedby="drone-latitude-hint"
          />
          <small id="drone-latitude-hint">{copy.live.droneLatitudeHint}</small>
        </label>
        <label htmlFor="drone-longitude">
          <span>{copy.live.droneLongitude}</span>
          <input
            id="drone-longitude"
            name="drone-longitude"
            type="text"
            inputMode="decimal"
            className="mono"
            value={droneTelemetry.longitude}
            onChange={setDroneField('longitude')}
            placeholder="9.518154"
            aria-describedby="drone-longitude-hint"
          />
          <small id="drone-longitude-hint">{copy.live.droneLongitudeHint}</small>
        </label>
        <label htmlFor="drone-altitude">
          <span>{copy.live.droneAltitude}</span>
          <input
            id="drone-altitude"
            name="drone-altitude"
            type="text"
            inputMode="decimal"
            className="mono"
            value={droneTelemetry.altitudeM}
            onChange={setDroneField('altitudeM')}
            placeholder="520"
            aria-describedby="drone-altitude-hint"
          />
          <small id="drone-altitude-hint">{copy.live.droneAltitudeHint}</small>
        </label>
      </div>

      <div className="metadata-prompt__footer">
        <p>{copy.live.metadataApplyHint}</p>
        <button
          type="button"
          className="primary-button metadata-prompt__apply"
          onClick={runBackendInference}
          disabled={!canApplyMetadata || isAnalyzing}
          title={
            !canApplyMetadata
              ? copy.live.applyDisabledNoMetadata
              : isAnalyzing
                ? copy.live.analyzing
                : copy.live.metadataApply
          }
        >
          {isAnalyzing ? copy.live.analyzing : copy.live.metadataApply}
        </button>
      </div>
    </div>
  )
}
