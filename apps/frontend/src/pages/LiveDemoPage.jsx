import clsx from 'clsx'
import { FrameStage } from '../components/FrameStage'
import { LampCropZoom } from '../components/LampCropZoom'
import { AnalysisHistoryPanel } from '../components/AnalysisHistoryPanel'
import { VideoConfidenceChart } from '../components/VideoConfidenceChart'
import { IDLE_SCENARIO } from '../catalog/scenarios'
import { useLiveDemo } from '../context/liveDemoContext'
import { FOLDER_MODE_ANGLE_SWEEP, FOLDER_MODE_SEQUENCE } from '../lib/analysisMode'
import { MediaUploadControls } from '../components/live/MediaUploadControls'
import { MetadataPrompt } from '../components/live/MetadataPrompt'
import { ActiveMetadataNotice } from '../components/live/ActiveMetadataNotice'
import { ResultPanel } from '../components/live/ResultPanel'
import { RunwaySelector } from '../components/live/RunwaySelector'

export function LiveDemoPage({ copy, plotTheme }) {
  // Analysis state comes from context (previously ~16 drilled props). The upload
  // controls, metadata prompt, and result panel are extracted components that read
  // the same context directly; the shell keeps only what the FrameStage viewer + the
  // folder-mode toggle + the trailing per-frame panels need.
  const {
    activeScenario,
    isAnalyzing,
    media,
    folderMode,
    setFolderMode,
    folderResultStale,
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
  } = useLiveDemo()

  // The Live Demo shows real backend output only. Until an analysis has run the
  // viewer shows the idle scenario and the trailing panels stay hidden.
  const hasResult = Boolean(backendScenario)

  return (
    <section className="demo-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.live.eyebrow}</p>
          <h2>{copy.live.title}</h2>
        </div>
        <MediaUploadControls copy={copy} />
      </div>

      <RunwaySelector copy={copy} />

      <ActiveMetadataNotice copy={copy} />

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
          {/* The shown result was produced in a different mode than the toggle now selects —
              prompt a re-run instead of letting the result drift silently (audit P1). */}
          {folderResultStale && (
            <p className="folder-mode__stale" role="status">
              {copy.live.folderModeStale}
            </p>
          )}
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

      <MetadataPrompt copy={copy} />

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

        <ResultPanel copy={copy} />
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
