import { useRef, useState } from 'react'
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Film,
  Pause,
  Play,
  Radar,
  RotateCcw,
  Upload,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import clsx from 'clsx'

export function FrameStage({
  scenario,
  media,
  analyzing,
  onFilesSelected,
  backendFrames,
  backendFrameIndex,
  onBackendFrameChange,
  folderVideo,
  canTransformFolderToVideo,
  transformingFolderVideo,
  onTransformFolderToVideo,
  onRestart,
  canRestart,
  restarting,
  artifactWarning,
  copy,
}) {
  const [isDragActive, setIsDragActive] = useState(false)
  const [viewerMode, setViewerMode] = useState('annotated')
  const [isZoomed, setIsZoomed] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const videoRef = useRef(null)
  const annotatedSource = scenario.artifactUrl
    ? { type: scenario.artifactType ?? 'image', url: scenario.artifactUrl }
    : media?.annotatedUrl
      ? { type: media.annotatedType ?? 'image', url: media.annotatedUrl }
      : null
  const originalSource =
    media?.url && media.type !== 'folder' ? { type: media.type, url: media.url } : null
  // Only offer the toggle when both an original upload and an annotated export exist.
  const canToggleView = Boolean(annotatedSource && originalSource)
  const displayMedia =
    folderVideo
      ? folderVideo
      : canToggleView && viewerMode === 'original'
      ? originalSource
      : annotatedSource ?? originalSource ?? media
  const canNavigateFrames = backendFrames.length > 1
  const canZoom = displayMedia?.type === 'image' || displayMedia?.type === 'video'
  const canControlVideo = displayMedia?.type === 'video'

  // Reset zoom/pause when the displayed media changes. Done during render (guarded by
  // the previous url) instead of in an effect — an effect here cascades an extra render
  // and trips react-hooks/set-state-in-effect (eslint error).
  const prevDisplayUrl = useRef(displayMedia?.url)
  if (prevDisplayUrl.current !== displayMedia?.url) {
    prevDisplayUrl.current = displayMedia?.url
    if (isZoomed) setIsZoomed(false)
    if (isPaused) setIsPaused(false)
  }

  // Reset the view toggle to the annotated export when a NEW analysis arrives.
  // Keyed on the underlying media (media?.url), NOT displayMedia?.url — the latter
  // changes on every toggle, so keying on it would instantly revert the user's choice.
  const prevMediaUrl = useRef(media?.url)
  if (prevMediaUrl.current !== media?.url) {
    prevMediaUrl.current = media?.url
    if (viewerMode !== 'annotated') setViewerMode('annotated')
  }

  const toggleVideoPlayback = () => {
    const video = videoRef.current
    if (!video) return

    if (video.paused) {
      video.play().then(() => setIsPaused(false)).catch(() => {})
    } else {
      video.pause()
      setIsPaused(true)
    }
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragActive(false)
    if (event.dataTransfer?.files?.length) {
      onFilesSelected?.(event.dataTransfer.files)
    }
  }

  const handleDragOver = (event) => {
    event.preventDefault()
    setIsDragActive(true)
  }

  const handleDragLeave = () => {
    setIsDragActive(false)
  }

  return (
    <div className={clsx('frame-stage', `frame-${scenario.environmentClass}`)}>
      <div className="frame-toolbar">
        {(scenario.frame || scenario.condition) && (
          <div className="frame-title">
            <span>{scenario.frame}</span>
            <span>{scenario.condition}</span>
          </div>
        )}
        {canToggleView && (
          <div className="frame-view-toggle" role="group" aria-label={copy.live.viewToggle}>
            <button
              type="button"
              className={clsx(viewerMode === 'annotated' && 'active')}
              aria-pressed={viewerMode === 'annotated'}
              onClick={() => setViewerMode('annotated')}
            >
              {copy.live.viewAnnotated}
            </button>
            <button
              type="button"
              className={clsx(viewerMode === 'original' && 'active')}
              aria-pressed={viewerMode === 'original'}
              onClick={() => setViewerMode('original')}
            >
              {copy.live.viewOriginal}
            </button>
          </div>
        )}
        {/* Viewer TOOLS (folder-video / play-pause / zoom / re-run) — labeled distinctly
            from the frame NAVIGATOR group below, which owns copy.live.frameNav (FE-14). */}
        <div className="frame-tool-controls" role="group" aria-label={copy.live.frameToolsLabel}>
          {canTransformFolderToVideo && (
            <button
              type="button"
              className={clsx('frame-transform-button', folderVideo && 'active')}
              onClick={onTransformFolderToVideo}
              disabled={transformingFolderVideo}
              aria-pressed={Boolean(folderVideo)}
              aria-label={folderVideo ? copy.live.folderVideoExit : copy.live.transformFolderVideo}
              title={folderVideo ? copy.live.folderVideoExit : copy.live.transformFolderVideo}
            >
              <Film size={16} />
              <span>
                {transformingFolderVideo
                  ? copy.live.folderVideoBuilding
                  : folderVideo
                    ? copy.live.folderVideoExit
                    : copy.live.transformFolderVideo}
              </span>
            </button>
          )}
          {canControlVideo && (
            <button
              type="button"
              onClick={toggleVideoPlayback}
              aria-label={isPaused ? copy.live.playVideo : copy.live.pauseVideo}
              title={isPaused ? copy.live.playVideo : copy.live.pauseVideo}
            >
              {isPaused ? <Play size={16} /> : <Pause size={16} />}
            </button>
          )}
          {canZoom && (
            <button
              type="button"
              className={clsx(isZoomed && 'active')}
              aria-pressed={isZoomed}
              onClick={() => setIsZoomed((current) => !current)}
              aria-label={isZoomed ? copy.live.zoomOut : copy.live.zoomIn}
              title={isZoomed ? copy.live.zoomOut : copy.live.zoomIn}
            >
              {isZoomed ? <ZoomOut size={16} /> : <ZoomIn size={16} />}
            </button>
          )}
          <button
            type="button"
            className="frame-restart-button"
            onClick={onRestart}
            disabled={!canRestart || restarting}
            aria-label={copy.live.restartAnalysis}
            title={
              !canRestart
                ? copy.live.restartDisabledNoMedia
                : restarting
                  ? copy.live.restartDisabledBusy
                  : copy.live.restartAnalysisLabel
            }
          >
            <RotateCcw size={16} />
            <span>{restarting ? copy.live.analyzing : copy.live.restartAnalysisLabel}</span>
          </button>
        </div>
        {canNavigateFrames && (
          <div className="frame-nav-controls" role="group" aria-label={copy.live.frameNav}>
            <button
              type="button"
              onClick={() => onBackendFrameChange?.(backendFrameIndex - 1)}
              disabled={backendFrameIndex === 0}
              aria-label={copy.live.previousFrame}
            >
              <ChevronLeft size={16} />
            </button>
            <strong>
              {backendFrameIndex + 1}/{backendFrames.length}
            </strong>
            <button
              type="button"
              onClick={() => onBackendFrameChange?.(backendFrameIndex + 1)}
              disabled={backendFrameIndex === backendFrames.length - 1}
              aria-label={copy.live.nextFrame}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
        {/* Annotated-preview fetch failed but the numeric analysis is on screen — show an
            inline badge so the gap isn't only a transient toast (audit F6). */}
        {artifactWarning && (
          <span className="frame-artifact-warning" role="status">
            <AlertTriangle size={13} aria-hidden="true" />
            {copy.live.artifactInlineWarning}
          </span>
        )}
      </div>

      <div
        className={clsx('video-surface', isZoomed && 'video-surface--zoomed')}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {displayMedia?.type === 'video' ? (
          // key on the URL so toggling annotated<->original remounts the <video>
          // and actually loads the new source (changing src alone does not reload
          // a media element per the HTML spec) (audit H3).
          <video
            ref={videoRef}
            key={displayMedia.url}
            src={displayMedia.url}
            aria-label={copy.live.frameAlt}
            autoPlay
            muted
            loop
            playsInline
            controls
            onPlay={() => setIsPaused(false)}
            onPause={() => setIsPaused(true)}
          />
        ) : displayMedia?.type === 'image' ? (
          <img key={displayMedia.url} src={displayMedia.url} alt={copy.live.frameAlt} />
        ) : analyzing ? (
          <div className="processing-placeholder" aria-hidden="true" />
        ) : (
          <DropzonePlaceholder
            isDragActive={isDragActive}
            onFilesSelected={onFilesSelected}
            copy={copy}
          />
        )}

        {analyzing && (
          <div className="analyzing-layer" role="status" aria-live="polite">
            <Radar size={34} />
            <span>{copy.live.backendInference}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function DropzonePlaceholder({ isDragActive, onFilesSelected, copy }) {
  // <label> + hidden <input> so the whole empty surface is one accessible
  // upload control: clicking anywhere (or Tab + Enter/Space) opens the native
  // picker, reusing the same handler and accept types as the LiveDemo upload
  // button. The drag-and-drop handlers live on the parent .video-surface, so
  // they keep working. event.target.value is cleared so picking the same file
  // twice still fires onChange.
  return (
    <label className={clsx('dropzone-placeholder', isDragActive && 'active')}>
      <input
        className="dropzone-input"
        accept="image/*,video/*"
        type="file"
        aria-label={copy.live.dropTitle}
        onChange={(event) => {
          onFilesSelected?.(event.target.files)
          event.target.value = ''
        }}
      />
      <div className="dropzone-card">
        <Upload size={28} />
        <strong>{copy.live.dropTitle}</strong>
        <span>{copy.live.dropText}</span>
      </div>
    </label>
  )
}
