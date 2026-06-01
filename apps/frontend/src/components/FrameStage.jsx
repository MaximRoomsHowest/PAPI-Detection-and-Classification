import { useState } from 'react'
import { ChevronLeft, ChevronRight, Radar, Upload } from 'lucide-react'
import clsx from 'clsx'

export function FrameStage({
  scenario,
  media,
  analyzing,
  onFilesSelected,
  backendFrames,
  backendFrameIndex,
  onBackendFrameChange,
  copy,
}) {
  const [isDragActive, setIsDragActive] = useState(false)
  const [viewerMode, setViewerMode] = useState('annotated')
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
    canToggleView && viewerMode === 'original'
      ? originalSource
      : annotatedSource ?? originalSource ?? media
  const canNavigateFrames = backendFrames.length > 1

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
          <div className="frame-view-toggle">
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
        {canNavigateFrames && (
          <div className="frame-nav-controls" aria-label={copy.live.frameNav}>
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
      </div>

      <div
        className="video-surface"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {displayMedia?.type === 'video' ? (
          // key on the URL so toggling annotated<->original remounts the <video>
          // and actually loads the new source (changing src alone does not reload
          // a media element per the HTML spec) (audit H3).
          <video key={displayMedia.url} src={displayMedia.url} autoPlay muted loop playsInline controls />
        ) : displayMedia?.type === 'image' ? (
          <img key={displayMedia.url} src={displayMedia.url} alt={copy.live.frameAlt} />
        ) : (
          <DropzonePlaceholder isDragActive={isDragActive} copy={copy} />
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

function DropzonePlaceholder({ isDragActive, copy }) {
  return (
    <div className={clsx('dropzone-placeholder', isDragActive && 'active')}>
      <div className="dropzone-card">
        <Upload size={28} />
        <strong>{copy.live.dropTitle}</strong>
        <span>{copy.live.dropText}</span>
      </div>
    </div>
  )
}
