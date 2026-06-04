import { FolderOpen, MapPin, Radar, Upload, X } from 'lucide-react'
import clsx from 'clsx'
import { FrameStage } from '../components/FrameStage'
import { LampCard } from '../components/LampCard'
import { InlineMetric } from '../components/InlineMetric'
import { LampCropZoom } from '../components/LampCropZoom'
import { AnalysisHistoryPanel } from '../components/AnalysisHistoryPanel'
import { VideoConfidenceChart } from '../components/VideoConfidenceChart'
import { IDLE_SCENARIO } from '../catalog/scenarios'
import { formatDurationMs } from '../lib/format'
import { useLiveDemo } from '../context/liveDemoContext'
import { FOLDER_MODE_ANGLE_SWEEP, FOLDER_MODE_SEQUENCE } from '../lib/analysisMode'

// Human-readable horizontal distance: metres under 1 km, else kilometres.
function formatDistanceM(meters) {
  if (meters == null) return ''
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`
}

export function LiveDemoPage({ copy, plotTheme }) {
  // Analysis state + the App-derived display objects come from context now
  // (previously ~16 drilled props). The destructured names match useAnalysis()'s
  // return exactly, so every reference below is unchanged. `onSelectRunway` /
  // `selectBackendFrame` keep their old local names by aliasing the hook fields.
  const {
    activeScenario,
    activeState,
    isAnalyzing,
    media,
    folderMode,
    setFolderMode,
    runways,
    selectedRunwayId,
    setSelectedRunwayId: onSelectRunway,
    backendScenario,
    backendFrames,
    backendFrameIndex,
    folderVideo,
    isTransformingFolderVideo,
    analysisError,
    analysisProgress,
    handleMediaFiles,
    runBackendInference,
    transformFolderToVideo,
    selectBackendFrame,
    handleMediaChange,
    droneTelemetry,
    setDroneTelemetry,
    metadataFile,
    setMetadataFile,
  } = useLiveDemo()

  const setDroneField = (field) => (event) =>
    setDroneTelemetry((current) => ({ ...current, [field]: event.target.value }))

  const handleMetadataFileChange = (event) => {
    setMetadataFile(event.target.files?.[0] ?? null)
    // Reset the input so re-selecting the same file still fires onChange.
    event.target.value = ''
  }

  // The Live Demo shows real backend output only. Until an analysis has run the
  // result panel stays empty rather than displaying a canned "demo" preset.
  const hasResult = Boolean(backendScenario)

  // The runway the *displayed* result was scored against — the backend echoes
  // runway_id on the payload, so this reflects what was actually analysed (not a
  // selector change made afterwards), mapped to its label.
  const usedRunwayId = activeScenario?.rawResult?.runway_id ?? selectedRunwayId
  const usedRunwayLabel =
    runways.find((runway) => runway.id === usedRunwayId)?.label ?? usedRunwayId
  const hasMissingAngleMetadata = hasResult && !activeScenario.angleSummary?.available
  const hasManualDroneTelemetry = Boolean(
    droneTelemetry.latitude.trim() &&
      droneTelemetry.longitude.trim() &&
      droneTelemetry.altitudeM.trim(),
  )
  const canApplyMetadata = Boolean(media && (metadataFile || hasManualDroneTelemetry))

  return (
    <section className="demo-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.live.eyebrow}</p>
          <h2>{copy.live.title}</h2>
        </div>
        <div className="demo-actions">
          <label className="upload-button">
            <Upload size={18} />
            <span>{media ? media.name : copy.live.upload}</span>
            <input
              id="papi-media-file"
              name="file"
              accept="image/*,video/*"
              type="file"
              aria-label={copy.live.upload}
              onChange={handleMediaChange}
            />
          </label>
          <label className="upload-button folder-upload">
            <FolderOpen size={18} />
            <span>{copy.live.uploadFolder}</span>
            <input
              id="papi-media-folder"
              name="files"
              accept="image/*"
              type="file"
              multiple
              webkitdirectory="true"
              directory=""
              onChange={handleMediaChange}
            />
          </label>
        </div>
      </div>

      {media?.type === 'folder' && (
        <div className="folder-mode" aria-live="polite">
          <span className="folder-mode__label">{copy.live.folderMode}</span>
          <div className="folder-mode__options" role="group" aria-label={copy.live.folderMode}>
            <button
              type="button"
              className={clsx(folderMode === FOLDER_MODE_ANGLE_SWEEP && 'active')}
              aria-pressed={folderMode === FOLDER_MODE_ANGLE_SWEEP}
              onClick={() => setFolderMode(FOLDER_MODE_ANGLE_SWEEP)}
            >
              {copy.live.folderAngleSweep}
            </button>
            <button
              type="button"
              className={clsx(folderMode === FOLDER_MODE_SEQUENCE && 'active')}
              aria-pressed={folderMode === FOLDER_MODE_SEQUENCE}
              onClick={() => setFolderMode(FOLDER_MODE_SEQUENCE)}
            >
              {copy.live.folderVideoSequence}
            </button>
          </div>
          <p>{copy.live.folderModeHint}</p>
        </div>
      )}

      {(analysisError || analysisProgress) && (
        <div
          className={clsx('analysis-status', analysisError && 'error')}
          role={analysisError ? 'alert' : 'status'}
          aria-live={analysisError ? 'assertive' : 'polite'}
        >
          {analysisError || analysisProgress}
        </div>
      )}

      {hasMissingAngleMetadata && (
        <div className="metadata-prompt" role="region" aria-labelledby="metadata-prompt-title">
          <div className="metadata-prompt__copy">
            <MapPin size={18} aria-hidden="true" />
            <div>
              <h3 id="metadata-prompt-title">{copy.live.metadataMissingTitle}</h3>
              <p>{copy.live.metadataMissingText}</p>
            </div>
          </div>

          <div className="metadata-prompt__controls">
            <label className="runway-select">
              <span>{copy.live.runway}</span>
              <select
                value={selectedRunwayId}
                onChange={(event) => onSelectRunway(event.target.value)}
                aria-label={copy.live.runway}
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
            </div>
          </div>

          <span className="drone-telemetry__divider">{copy.live.telemetryOrManual}</span>

          <div className="drone-telemetry__fields">
            <label>
              <span>{copy.live.droneLatitude}</span>
              <input
                type="text"
                inputMode="decimal"
                className="mono"
                value={droneTelemetry.latitude}
                onChange={setDroneField('latitude')}
                placeholder="47.673521"
              />
            </label>
            <label>
              <span>{copy.live.droneLongitude}</span>
              <input
                type="text"
                inputMode="decimal"
                className="mono"
                value={droneTelemetry.longitude}
                onChange={setDroneField('longitude')}
                placeholder="9.518154"
              />
            </label>
            <label>
              <span>{copy.live.droneAltitude}</span>
              <input
                type="text"
                inputMode="decimal"
                className="mono"
                value={droneTelemetry.altitudeM}
                onChange={setDroneField('altitudeM')}
                placeholder="520"
              />
            </label>
          </div>

          <div className="metadata-prompt__footer">
            <p>{copy.live.metadataApplyHint}</p>
            <button
              type="button"
              className="primary-button metadata-prompt__apply"
              onClick={runBackendInference}
              disabled={!canApplyMetadata || isAnalyzing}
            >
              {isAnalyzing ? copy.live.analyzing : copy.live.metadataApply}
            </button>
          </div>
        </div>
      )}

      <div className="live-grid">
        <div className="frame-tool frame-tool--enter">
          <FrameStage
            scenario={hasResult ? activeScenario : IDLE_SCENARIO}
            media={media}
            analyzing={isAnalyzing}
            onFilesSelected={handleMediaFiles}
            backendFrames={backendFrames}
            backendFrameIndex={backendFrameIndex}
            onBackendFrameChange={selectBackendFrame}
            folderVideo={folderVideo}
            canTransformFolderToVideo={media?.type === 'folder'}
            transformingFolderVideo={isTransformingFolderVideo}
            onTransformFolderToVideo={transformFolderToVideo}
            onRestart={runBackendInference}
            canRestart={Boolean(media)}
            restarting={isAnalyzing}
            copy={copy}
          />
        </div>

        <aside className="analysis-panel" id="analysis-details">
          {hasResult ? (
            <>
              <div className="state-summary">
                <span className="status-dot" style={{ '--dot-color': activeState.color }} />
                <div>
                  <p>{activeScenario.summary}</p>
                  <h3>{activeState.label}</h3>
                  <small>{activeState.description}</small>
                  {/* On an "unknown" verdict, show how many of the 4 lamps were
                      actually detected so the result reads as "found 3, one was
                      too faint" rather than a total miss (the yolo26s model is
                      precise but conservative on dim/distant lamps). */}
                  {activeScenario.stateId === 'unknown' && (
                    <small className="state-summary__count">
                      {copy.live.lampsDetected
                        .replace(
                          '{n}',
                          activeScenario.lamps.filter(
                            (lamp) => lamp.status === 'red' || lamp.status === 'white',
                          ).length,
                        )
                        .replace('{total}', activeScenario.lamps.length)}
                    </small>
                  )}
                </div>
              </div>

              <div className="lamp-list">
                {activeScenario.lamps.map((lamp) => (
                  <LampCard key={lamp.id} lamp={lamp} copy={copy} />
                ))}
              </div>

              {/* Real backend metrics only — detection confidence + processing time. */}
              <div className="metric-grid metric-grid--compact">
                <InlineMetric
                  label={copy.live.detection}
                  value={activeScenario.metrics.boxConfidence}
                  suffix="%"
                />
                <InlineMetric
                  label={copy.live.latency}
                  value={formatDurationMs(activeScenario.metrics.latency).value}
                  suffix={formatDurationMs(activeScenario.metrics.latency).suffix}
                />
              </div>

              {/* PAPI elevation angle — real WGS-84 geometry from the drone GPS /
                  manual telemetry vs the runway's surveyed lamps. "Unavailable"
                  when no drone position was supplied or read from EXIF. */}
              <div
                className={clsx(
                  'angle-readout',
                  !activeScenario.angleSummary?.available && 'unavailable',
                  activeScenario.angleSummary?.available &&
                    activeScenario.angleSummary?.plausible === false &&
                    'implausible',
                )}
              >
                <span>{copy.live.elevationAngle}</span>
                {activeScenario.angleSummary?.available ? (
                  <>
                    <strong className="tnum">
                      {activeScenario.angleSummary.value}
                      <small>°</small>
                      {/* RTK 1-sigma band — only present when the file carried DJI
                          RTK std, so it never fabricates a confidence figure. */}
                      {activeScenario.angleSummary.uncertainty != null && (
                        <small className="angle-readout__band">
                          ± {activeScenario.angleSummary.uncertainty}° {copy.live.angleUncertainty}
                        </small>
                      )}
                    </strong>
                    {/* Provenance of the position, localized in translateScenario:
                        "from your input" / "from image GPS" / "from telemetry file". */}
                    <p>{activeScenario.angleSummary.source}</p>
                    {/* Which runway the angle was scored against + how far the drone
                        was from it — the runway<->metadata relationship, made explicit. */}
                    <p className="angle-readout__context">
                      {copy.live.runwayUsed.replace('{runway}', usedRunwayLabel)}
                      {activeScenario.angleSummary.nearestLampDistanceM != null &&
                        ` · ${copy.live.nearestLampDistance.replace(
                          '{distance}',
                          formatDistanceM(activeScenario.angleSummary.nearestLampDistanceM),
                        )}`}
                    </p>
                    {activeScenario.angleSummary.plausible === false && (
                      <p className="angle-readout__warning" role="alert">
                        {copy.live.angleImplausible}
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <strong>{copy.live.angleUnavailable}</strong>
                    <p>{copy.live.angleHint}</p>
                  </>
                )}
              </div>

              {activeScenario.transitions?.length > 0 && (
                <div className="transition-readout">
                  <span>{copy.live.transitionsHeading}</span>
                  <ul>
                    {activeScenario.transitions.map((event, index) => (
                      <li key={`${event.lamp_index}-${event.frame_index}-${index}`}>
                        {`${copy.live.light} ${event.lamp_index}: `}
                        {`${copy.status?.[event.from_state] ?? event.from_state} → ${copy.status?.[event.to_state] ?? event.to_state}`}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="analysis-empty">
              <Radar size={28} />
              <p>{copy.live.emptyState}</p>
            </div>
          )}
        </aside>
      </div>

      {/* Per-frame detection history — only for multi-image uploads, where each
          extracted frame has its own scenario to step through. Folders/videos
          collapse to one aggregated result (backendFrames is empty), so no
          history is shown. Selecting a row drives the whole result panel above. */}
      {hasResult && backendFrames.length > 1 && (
        <AnalysisHistoryPanel
          activeScenario={activeScenario}
          backendFrames={backendFrames}
          backendFrameIndex={backendFrameIndex}
          onSelectFrame={selectBackendFrame}
          copy={copy}
        />
      )}

      {/* PAPI close-up: high-res frames hide the lamp states, so reframe to the
          detected boxes for visual verification. Image uploads only — folder
          frames and videos use their backend-annotated artifact + the
          transition/angle charts on Insights. */}
      {hasResult && media?.type === 'image' && (
        <LampCropZoom
          imageUrl={media.url}
          naturalWidth={media.naturalWidth}
          naturalHeight={media.naturalHeight}
          lamps={activeScenario.lamps}
          copy={copy}
        />
      )}

      {/* Frame-by-frame detection confidence — shown for any backend payload with
          a per-frame series: videos and folder-as-video sequences. Angle-sweep
          folders are surfaced as per-image history + angle-vs-state charts. */}
      {hasResult && activeScenario.perFrame?.length > 0 && (
        <VideoConfidenceChart perFrame={activeScenario.perFrame} plotTheme={plotTheme} copy={copy} />
      )}
    </section>
  )
}
