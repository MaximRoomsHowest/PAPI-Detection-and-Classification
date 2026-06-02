import { FolderOpen, Radar, Upload, Zap } from 'lucide-react'
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
    runways,
    selectedRunwayId,
    setSelectedRunwayId: onSelectRunway,
    backendScenario,
    backendFrames,
    backendFrameIndex,
    analysisError,
    analysisProgress,
    handleMediaFiles,
    runBackendInference,
    selectBackendFrame,
    handleMediaChange,
  } = useLiveDemo()

  // The Live Demo shows real backend output only. Until an analysis has run the
  // result panel stays empty rather than displaying a canned "demo" preset.
  const hasResult = Boolean(backendScenario)

  return (
    <section className="demo-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.live.eyebrow}</p>
          <h2>{copy.live.title}</h2>
        </div>
        <div className="demo-actions">
          <label className="runway-select">
            <span>{copy.live.runway}</span>
            <select
              value={selectedRunwayId}
              onChange={(event) => onSelectRunway(event.target.value)}
              aria-label={copy.live.runway}
            >
              {/* Keep the chosen id selectable before the list loads so the
                  control never renders blank on first paint. */}
              {runways.length === 0 && <option value={selectedRunwayId}>{selectedRunwayId}</option>}
              {runways.map((runway) => (
                <option key={runway.id} value={runway.id}>
                  {runway.label ?? runway.id}
                </option>
              ))}
            </select>
          </label>
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
          <button
            className="primary-button"
            type="button"
            onClick={runBackendInference}
            disabled={!media || isAnalyzing}
          >
            <Zap size={18} />
            {isAnalyzing ? copy.live.analyzing : copy.live.runModel}
          </button>
        </div>
      </div>

      {(analysisError || analysisProgress) && (
        <div
          className={clsx('analysis-status', analysisError && 'error')}
          role={analysisError ? 'alert' : 'status'}
          aria-live={analysisError ? 'assertive' : 'polite'}
        >
          {analysisError || analysisProgress}
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
            copy={copy}
          />
        </div>

        <aside className="analysis-panel">
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

      {/* Frame-by-frame detection confidence — video uploads only, where the
          backend returns a per-frame series. A geotagged image folder is instead
          analyzed per-image (each with its own angle) and surfaced as the per-lamp
          angle-vs-state + transition-angle charts on the Insights page. */}
      {hasResult && media?.type === 'video' && activeScenario.perFrame?.length > 0 && (
        <VideoConfidenceChart perFrame={activeScenario.perFrame} plotTheme={plotTheme} copy={copy} />
      )}
    </section>
  )
}
