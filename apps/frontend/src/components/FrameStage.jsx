import { useRef, useState } from 'react'
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Film,
  Images,
  Pause,
  Play,
  Radar,
  RotateCcw,
  Upload,
  Video,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import clsx from 'clsx'
import { toast } from 'sonner'
import { FOLDER_MODE_SEQUENCE } from '../lib/analysisMode'

const SAMPLE_RUNWAY_ID = 'papi_24'
const SAMPLE_METADATA_FILE = {
  url: '/demo-samples/sample-descent.json',
  name: 'sample-descent.json',
  type: 'application/json',
}

// Labels/descriptions are i18n keys under copy.live (resolved at render time)
// so the picker follows the active locale like every other Live-Demo string.
const SAMPLE_MEDIA = [
  {
    id: 'single-frame',
    labelKey: 'sampleSingleImageLabel',
    descriptionKey: 'sampleSingleImageDescription',
    icon: Images,
    files: [{ url: '/demo-samples/papi-test-frame.jpg', name: 'papi-test-frame.jpg', type: 'image/jpeg' }],
    metadataFile: SAMPLE_METADATA_FILE,
  },
  {
    id: 'image-sequence',
    labelKey: 'sampleImageSetLabel',
    descriptionKey: 'sampleImageSetDescription',
    icon: Images,
    folderMode: FOLDER_MODE_SEQUENCE,
    files: [
      {
        url: '/demo-samples/folder-frame-001.jpg',
        name: 'frame_001.jpg',
        type: 'image/jpeg',
        path: 'sample-papi-frames/frame_001.jpg',
      },
      {
        url: '/demo-samples/folder-frame-002.jpg',
        name: 'frame_002.jpg',
        type: 'image/jpeg',
        path: 'sample-papi-frames/frame_002.jpg',
      },
      {
        url: '/demo-samples/folder-frame-003.jpg',
        name: 'frame_003.jpg',
        type: 'image/jpeg',
        path: 'sample-papi-frames/frame_003.jpg',
      },
      {
        url: '/demo-samples/folder-frame-004.jpg',
        name: 'frame_004.jpg',
        type: 'image/jpeg',
        path: 'sample-papi-frames/frame_004.jpg',
      },
      {
        url: '/demo-samples/folder-frame-005.jpg',
        name: 'frame_005.jpg',
        type: 'image/jpeg',
        path: 'sample-papi-frames/frame_005.jpg',
      },
    ],
    metadataFile: SAMPLE_METADATA_FILE,
  },
  {
    id: 'short-video',
    labelKey: 'sampleVideoLabel',
    descriptionKey: 'sampleVideoDescription',
    icon: Video,
    files: [
      {
        url: '/demo-samples/daytime-approach-smoke.mp4',
        name: 'daytime-approach-smoke.mp4',
        type: 'video/mp4',
      },
    ],
    metadataFile: SAMPLE_METADATA_FILE,
  },
]

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
  const timelineFrameCount =
    displayMedia?.type === 'video'
      ? (scenario.perFrame?.length || scenario.rawResult?.angle_track?.length || folderVideo?.frameCount || 0)
      : 0
  const frameNavCount = backendFrames.length || timelineFrameCount
  const canNavigateFrames = frameNavCount > 1
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

  const seekVideoToFrame = (index) => {
    const video = videoRef.current
    if (!video || !timelineFrameCount || !Number.isFinite(video.duration) || video.duration <= 0) {
      return
    }

    const clamped = Math.min(Math.max(index, 0), timelineFrameCount - 1)
    video.currentTime = (clamped / timelineFrameCount) * video.duration
  }

  const selectFrame = (index) => {
    seekVideoToFrame(index)
    onBackendFrameChange?.(index)
  }

  const syncVideoFrame = () => {
    const video = videoRef.current
    if (!video || !timelineFrameCount || !Number.isFinite(video.duration) || video.duration <= 0) {
      return
    }

    const progress = video.currentTime / video.duration
    const nextIndex = Math.min(
      timelineFrameCount - 1,
      Math.max(0, Math.floor(progress * timelineFrameCount)),
    )

    if (nextIndex !== backendFrameIndex) {
      onBackendFrameChange?.(nextIndex)
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
              onClick={() => selectFrame(backendFrameIndex - 1)}
              disabled={backendFrameIndex === 0}
              aria-label={copy.live.previousFrame}
            >
              <ChevronLeft size={16} />
            </button>
            <strong>
              {backendFrameIndex + 1}/{frameNavCount}
            </strong>
            <button
              type="button"
              onClick={() => selectFrame(backendFrameIndex + 1)}
              disabled={backendFrameIndex === frameNavCount - 1}
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
            onTimeUpdate={syncVideoFrame}
            onSeeked={syncVideoFrame}
            onLoadedMetadata={syncVideoFrame}
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
  const [loadingSampleId, setLoadingSampleId] = useState(null)

  async function fileFromSampleAsset(sampleFile) {
    const response = await fetch(sampleFile.url)
    if (!response.ok) {
      throw new Error(`Could not load ${sampleFile.name}`)
    }

    const blob = await response.blob()
    // No explicit lastModified: the File constructor defaults it to "now", and
    // an inline Date.now() trips the react-hooks/purity compiler lint.
    const file = new File([blob], sampleFile.name, {
      type: sampleFile.type || blob.type,
    })

    if (sampleFile.path) {
      Object.defineProperty(file, 'webkitRelativePath', {
        configurable: true,
        value: sampleFile.path,
      })
    }

    return file
  }

  async function loadSample(sample) {
    if (loadingSampleId) {
      return
    }

    setLoadingSampleId(sample.id)
    try {
      const files = await Promise.all(sample.files.map(fileFromSampleAsset))
      const metadataFile = sample.metadataFile ? await fileFromSampleAsset(sample.metadataFile) : null

      onFilesSelected?.(files, {
        folderMode: sample.folderMode,
        metadataFile,
        runwayId: SAMPLE_RUNWAY_ID,
        sampleMetadata: Boolean(metadataFile),
      })
    } catch {
      // A failed asset fetch (offline, mis-deployed sample) must surface to the
      // user — an unhandled rejection here left the button silently dead.
      toast.error(copy.live.sampleLoadFailed)
    } finally {
      setLoadingSampleId(null)
    }
  }

  return (
    <div className={clsx('dropzone-placeholder', isDragActive && 'active')}>
      <div className="dropzone-card">
        <Upload size={28} />
        <strong>{copy.live.dropTitle}</strong>
        <span>{copy.live.dropText}</span>
        <label className="dropzone-upload-button">
          <Upload size={16} />
          <span>{copy.live.uploadOwnData}</span>
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
        </label>
        <div className="sample-picker" role="group" aria-label={copy.live.samplePickerTitle}>
          <span className="sample-picker__title">{copy.live.samplePickerTitle}</span>
          <div className="sample-picker__grid">
            {SAMPLE_MEDIA.map((sample) => {
              const SampleIcon = sample.icon
              const isLoading = loadingSampleId === sample.id

              return (
                <button
                  key={sample.id}
                  type="button"
                  className="sample-picker__button"
                  disabled={Boolean(loadingSampleId)}
                  onClick={() => loadSample(sample)}
                >
                  <SampleIcon size={16} />
                  <span>
                    <strong>{isLoading ? copy.live.sampleLoading : copy.live[sample.labelKey]}</strong>
                    <small>{copy.live[sample.descriptionKey]}</small>
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
