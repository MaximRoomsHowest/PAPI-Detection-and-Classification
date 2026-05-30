import { FolderOpen, Radar, Upload, Zap } from 'lucide-react'
import clsx from 'clsx'
import { FrameStage } from '../components/FrameStage'
import { LampCard } from '../components/LampCard'
import { InlineMetric } from '../components/InlineMetric'
import { IDLE_SCENARIO } from '../catalog/scenarios'

export function LiveDemoPage({
  activeScenario,
  activeState,
  isAnalyzing,
  media,
  backendScenario,
  backendFrames,
  backendFrameIndex,
  analysisError,
  analysisProgress,
  handleMediaFiles,
  runBackendInference,
  selectBackendFrame,
  handleMediaChange,
  copy,
}) {
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
          <label className="upload-button">
            <Upload size={18} />
            <span>{media ? media.name : copy.live.upload}</span>
            <input
              id="papi-media-file"
              name="file"
              accept="image/*,video/*"
              type="file"
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
                  value={activeScenario.metrics.latency}
                  suffix=" ms"
                />
              </div>

              {activeScenario.transitions?.length > 0 && (
                <div className="transition-readout">
                  <span>{copy.live.transitionsHeading}</span>
                  <ul>
                    {activeScenario.transitions.map((event, index) => (
                      <li key={`${event.lamp_index}-${event.frame_index}-${index}`}>
                        {`${copy.live.lamp} ${event.lamp_index}: `}
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
    </section>
  )
}
