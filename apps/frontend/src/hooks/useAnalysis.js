import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  analyzeFrame,
  analyzeMedia,
  analyzeSequence,
  createRunway,
  deleteRunway as deleteRunwayRequest,
  fetchRunways,
  resolveMediaUrl,
  revokeMediaUrl,
} from '../lib/api'
import { useFetch } from './useFetch'
import { extractFrameImages } from '../lib/frameExtraction'
import { loadPlotlyBundle } from '../lib/plotlyBundle'
import { isImageFile, isVideoFile, fileDisplayPath } from '../lib/fileType'
import { scenarioFromBackendResult } from '../lib/papi'
import { resolveRunwayId } from '../lib/runwaySelection'
import { STORAGE_KEYS, safeLocalStorageSet, initialRunwayId } from '../lib/storage'
import { createFolderVideo } from '../lib/folderVideo'
import {
  FOLDER_MODE_ANGLE_SWEEP,
  metadataFileForAnalysis,
  shouldAnalyzeFolderAsSequence,
  shouldKeepFrameScenarios,
} from '../lib/analysisMode'

// Client-side mirror of the backend PAPI_MAX_BATCH_FRAMES cap so an oversized folder is
// rejected up front instead of uploading the whole batch only to be 413'd (audit).
const MAX_BATCH_FRAMES = Number(import.meta.env.VITE_PAPI_MAX_BATCH_FRAMES) || 200

// Owns the Live-Demo upload + backend-inference state and the handlers that drive
// it — extracted from App.jsx so the App component is just the route shell. `copy`
// is the active-locale i18n object; every user-facing string is read from it.
export function useAnalysis(copy) {
  const [activeId, setActiveId] = useState('clean')
  const [media, setMedia] = useState(null)
  const [folderMode, setFolderMode] = useState(FOLDER_MODE_ANGLE_SWEEP)
  // Runway selection: the list comes from the backend (/api/runways); the chosen
  // id is sent as `runway_id` so the analysis scores against the right PAPI unit's
  // surveyed geometry. The id is persisted across reloads (localStorage) and
  // reconciled against the live list, so a stored/selected id that no longer exists
  // (custom runway deleted in another tab) self-heals to a safe default instead of
  // silently breaking the selector and the analyze call.
  const { data: runwayData, refetch: refetchRunways } = useFetch(fetchRunways, [])
  // Memoised so its identity is stable across renders — an inline `?? []` makes a
  // new array every render, which would churn the dependent memo/effect below.
  const runways = useMemo(() => runwayData ?? [], [runwayData])
  const [selectedRunwayId, setSelectedRunwayId] = useState(initialRunwayId)

  // Effective selection: the stored id reconciled against the live list. A
  // stale/deleted id (e.g. a custom runway removed in another tab) transparently
  // resolves to a safe default — DERIVED, not stored, so we never setState in an
  // effect (which cascades renders). Before the list loads we keep the raw id so the
  // persisted choice isn't clobbered by the empty-list fallback.
  const effectiveRunwayId =
    runways.length > 0 ? resolveRunwayId(selectedRunwayId, runways) : selectedRunwayId

  // Persist the effective id (best-effort; safe in private-mode / SSR) so a stale
  // stored id self-heals on disk too once the live list is known.
  useEffect(() => {
    safeLocalStorageSet(STORAGE_KEYS.runway, effectiveRunwayId)
  }, [effectiveRunwayId])

  // The full record for the selected runway, shared app-wide so the Live Demo and
  // Runways page can show its label + geometry (not just the id).
  const selectedRunway = useMemo(
    () => runways.find((runway) => runway.id === effectiveRunwayId) ?? null,
    [runways, effectiveRunwayId],
  )

  // Runway management, shared app-wide via context so the Runways page and the
  // Live Demo selector stay in sync. A newly added runway is persisted server-side
  // and immediately usable for analysis, so refetch the list and make it active;
  // deleting the active runway falls back to the backend default (papi_24).
  async function addRunway(payload) {
    const created = await createRunway(payload)
    refetchRunways()
    setSelectedRunwayId(created.id)
    return created
  }

  async function removeRunway(runwayId) {
    await deleteRunwayRequest(runwayId)
    refetchRunways()
    // Fall off the deleted runway to a still-valid one. papi_24 is a built-in
    // (undeletable), so resolveRunwayId always yields a valid id; the reconciliation
    // effect is the backstop once the refetched list arrives.
    setSelectedRunwayId((current) =>
      current === runwayId
        ? resolveRunwayId(null, runways.filter((runway) => runway.id !== runwayId))
        : current,
    )
  }

  // Optional manual drone telemetry for the elevation-angle calc, used when an
  // uploaded image carries no GPS EXIF (browser uploads usually strip it). Empty
  // strings mean "not provided": the backend then falls back to the file's EXIF,
  // then to angle-unavailable. Sent only when all three are present (the backend
  // requires lat + lon + altitude together).
  const [droneTelemetry, setDroneTelemetry] = useState({ latitude: '', longitude: '', altitudeM: '' })

  // Optional drone-telemetry FILE (DJI .SRT / CSV / JSON) paired with the upload.
  // Parsed server-side into drone fixes that take priority over the manual fields
  // and the media's embedded EXIF; for a video it powers the per-frame angle track
  // (the red->white sweep on Insights). Like the manual fields it is an INPUT, so it
  // persists across media changes — the user can pick the file before or after the
  // media and clears it explicitly.
  const [metadataFile, setMetadataFile] = useState(null)

  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const [backendScenario, setBackendScenario] = useState(null)
  const [backendFrames, setBackendFrames] = useState([])
  // Raw AnalysisPayload[] kept in parallel with backendFrames so result-driven
  // views (crop/zoom, angle-vs-state, transition charts) read bbox/per-light
  // angles/transitions straight from the backend instead of the display scenario.
  const [backendResults, setBackendResults] = useState([])
  const [backendFrameIndex, setBackendFrameIndex] = useState(0)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisProgress, setAnalysisProgress] = useState('')
  const [autoRunRequested, setAutoRunRequested] = useState(false)
  const [folderVideo, setFolderVideo] = useState(null)
  const [isTransformingFolderVideo, setIsTransformingFolderVideo] = useState(false)
  const insightsRef = useRef(null)
  // Monotonic analysis run id: bumped whenever new media is selected and captured
  // at the start of each run, so a slow in-flight analysis whose media was replaced
  // mid-flight discards its (now stale) result instead of painting it onto the new
  // upload (audit frontend-bugs: mid-analysis file swap).
  const runIdRef = useRef(0)
  const resolvedArtifactUrlsRef = useRef([])

  useEffect(() => {
    return () => {
      if (media?.url) {
        URL.revokeObjectURL(media.url)
      }
    }
  }, [media?.url])

  useEffect(() => {
    return () => {
      if (folderVideo?.url) {
        URL.revokeObjectURL(folderVideo.url)
      }
    }
  }, [folderVideo?.url])

  useEffect(() => {
    return () => {
      resolvedArtifactUrlsRef.current.forEach(revokeMediaUrl)
      resolvedArtifactUrlsRef.current = []
    }
  }, [])

  function clearResolvedArtifactUrls() {
    resolvedArtifactUrlsRef.current.forEach(revokeMediaUrl)
    resolvedArtifactUrlsRef.current = []
  }

  function clearFolderVideo() {
    setFolderVideo((current) => {
      if (current?.url) {
        URL.revokeObjectURL(current.url)
      }
      return null
    })
  }

  async function resolveResultArtifactUrls(results, runId) {
    const createdUrls = []
    const urls = []

    try {
      for (const result of results) {
        if (runIdRef.current !== runId) {
          createdUrls.forEach(revokeMediaUrl)
          return null
        }

        const url = await resolveMediaUrl(result.artifact_url)

        if (runIdRef.current !== runId) {
          revokeMediaUrl(url)
          createdUrls.forEach(revokeMediaUrl)
          return null
        }

        if (url?.startsWith('blob:')) {
          createdUrls.push(url)
        }
        urls.push(url)
      }
    } catch (error) {
      createdUrls.forEach(revokeMediaUrl)
      throw error
    }

    return { urls, createdUrls }
  }

  function handleMediaFiles(files) {
    const selectedFiles = Array.from(files ?? [])
    if (!selectedFiles.length) {
      return
    }

    const imageFiles = selectedFiles
      .filter(isImageFile)
      .sort((first, second) => fileDisplayPath(first).localeCompare(fileDisplayPath(second), undefined, { numeric: true }))
    const isFolderBatch = imageFiles.length > 1
    const file = isFolderBatch ? imageFiles[0] : selectedFiles[0]

    // Client-side validation: the <input accept="..."> attribute is only a
    // picker hint, not a hard filter. A user can still pick "All files" and
    // upload anything. Without this guard we'd generate a blob URL for the
    // wrong content type, briefly render e.g. a text file as if it were an
    // image, and only fail once the backend returned 400 (regression
    // USERTEST-MAJ-1, papi-user-test-2026-05-28).
    if (!isFolderBatch && !isImageFile(file) && !isVideoFile(file)) {
      // Clear any prior result so a stale result panel doesn't sit under the
      // "unsupported file" error as if it belonged to the rejected file (audit FB-03).
      runIdRef.current += 1
      clearResolvedArtifactUrls()
      setIsAnalyzing(false)
      setBackendScenario(null)
      setBackendFrames([])
      setBackendResults([])
      setBackendFrameIndex(0)
      clearFolderVideo()
      setAnalysisProgress('')
      setAnalysisError(copy.live.unsupportedFile.replace('{name}', () => file.name))
      return
    }

    const url = URL.createObjectURL(file)

    setMedia((previous) => {
      if (previous?.url) {
        URL.revokeObjectURL(previous.url)
      }

      return {
        file,
        files: isFolderBatch ? imageFiles : null,
        name: isFolderBatch
          ? `${fileDisplayPath(imageFiles[0]).split('/')[0]} (${imageFiles.length} images)`
          : file.name,
        type: isFolderBatch ? 'folder' : isVideoFile(file) ? 'video' : 'image',
        url,
        annotatedUrl: null,
      }
    })
    // Invalidate any in-flight analysis so its result is not applied to this
    // newly selected media.
    runIdRef.current += 1
    clearResolvedArtifactUrls()
    setIsAnalyzing(false)
    setBackendScenario(null)
    setBackendFrames([])
    setBackendResults([])
    setBackendFrameIndex(0)
    clearFolderVideo()
    setAnalysisError('')
    setAnalysisProgress('')
    setAutoRunRequested(true)

    // Read the intrinsic pixel size of a single image up front so the
    // crop/zoom verification view can map the backend's bbox coordinates
    // (original-image pixels) to the rendered crop without a second load. The
    // url-equality guard prevents a slow decode from patching a newer upload.
    if (!isFolderBatch && isImageFile(file)) {
      const probe = new window.Image()
      probe.onload = () => {
        setMedia((current) =>
          current && current.url === url
            ? { ...current, naturalWidth: probe.naturalWidth, naturalHeight: probe.naturalHeight }
            : current,
        )
      }
      // Release the decode buffer / let the element be GC'd if the blob fails to
      // load; without this the probe leaks and the crop view never gets its dims.
      probe.onerror = () => {
        probe.src = ''
      }
      probe.src = url
    }
  }

  function handleMediaChange(event) {
    handleMediaFiles(event.target.files)
    event.target.value = ''
  }

  useEffect(() => {
    if (!autoRunRequested || !media?.file || isAnalyzing) {
      return
    }

    setAutoRunRequested(false)
    const timeoutId = window.setTimeout(() => {
      runBackendInference()
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [autoRunRequested, media?.file, isAnalyzing])

  function selectBackendFrame(index) {
    if (!backendFrames.length) {
      return
    }

    const nextIndex = Math.min(Math.max(index, 0), backendFrames.length - 1)
    setBackendFrameIndex(nextIndex)
    setBackendScenario(backendFrames[nextIndex])
    setActiveId('backend')
  }

  async function transformFolderToVideo() {
    if (media?.type !== 'folder' || isTransformingFolderVideo) {
      return
    }

    const annotatedSources = backendFrames
      .map((frame, index) =>
        frame.artifactUrl
          ? {
              url: frame.artifactUrl,
              label: frame.frame ?? `${copy.live.frameAxis} ${index + 1}`,
            }
          : null,
      )
      .filter(Boolean)

    const originalSources = (media.files ?? []).map((file) => ({
      file,
      label: fileDisplayPath(file),
    }))

    const sources = annotatedSources.length > 1 ? annotatedSources : originalSources

    if (sources.length < 2) {
      toast.error(copy.live.folderVideoNeedsImages)
      return
    }

    setIsTransformingFolderVideo(true)
    try {
      const result = await createFolderVideo(sources)
      clearFolderVideo()
      setFolderVideo({
        url: result.url,
        type: 'video',
        name: copy.live.folderVideoName.replace('{count}', String(result.frameCount)),
        frameCount: result.frameCount,
        fps: result.fps,
        source: annotatedSources.length > 1 ? 'annotated' : 'original',
      })
      toast.success(copy.live.folderVideoReady)
    } catch (error) {
      toast.error(error.message || copy.live.folderVideoFailed)
    } finally {
      setIsTransformingFolderVideo(false)
    }
  }

  async function handleDownloadCharts() {
    if (!insightsRef.current || isExporting) {
      return
    }

    setIsExporting(true)
    setExportError('')

    try {
      const { jsPDF } = await import('jspdf')
      const { Plotly } = await loadPlotlyBundle()
      const chartNodes = Array.from(
        insightsRef.current.querySelectorAll('.js-plotly-plot'),
      )

      if (!chartNodes.length) {
        // No rendered charts to capture — tell the user instead of silently
        // doing nothing (audit F06/F07).
        setExportError(copy.insights.downloadUnavailable)
        return
      }

      const images = []
      for (const node of chartNodes) {
        const rect = node.getBoundingClientRect()
        const width = Math.max(1, Math.round(rect.width))
        const height = Math.max(1, Math.round(rect.height))
        const dataUrl = await Plotly.toImage(node, {
          format: 'png',
          width,
          height,
          scale: 2,
        })
        images.push({
          dataUrl,
          width,
          height,
          orientation: width >= height ? 'landscape' : 'portrait',
        })
      }

      const [first, ...rest] = images
      const pdf = new jsPDF({
        orientation: first.orientation,
        unit: 'px',
        format: [first.width, first.height],
      })
      pdf.addImage(first.dataUrl, 'PNG', 0, 0, first.width, first.height)
      rest.forEach((image) => {
        pdf.addPage([image.width, image.height], image.orientation)
        pdf.addImage(image.dataUrl, 'PNG', 0, 0, image.width, image.height)
      })
      pdf.save('papi-vision-insights.pdf')
      toast.success(copy.insights.downloadReady)
    } catch (error) {
      console.error('PDF export failed', error)
      setExportError(copy.insights.downloadFailed)
      toast.error(copy.insights.downloadFailed)
    } finally {
      setIsExporting(false)
    }
  }

  async function runBackendInference() {
    if (!media?.file || isAnalyzing) {
      return
    }

    const runId = ++runIdRef.current
    setIsAnalyzing(true)
    setAnalysisError('')

    try {
      let bestScenario = null
      let bestIndex = 0
      let rawResults = []
      const frameContexts = []
      const currentFolderMode = folderMode
      const keepsFrameScenarios = shouldKeepFrameScenarios(media.type, currentFolderMode)
      // Telemetry sent with every analyze call. runway_id selects which PAPI
      // unit's geometry the backend scores + computes elevation angles against.
      // Manual drone lat/lon/altitude is included only when ALL three are filled
      // (the backend rejects a partial set); empty fields are omitted by api.js so
      // the backend falls back to the image's EXIF, then to angle-unavailable.
      const hasDroneTelemetry = Boolean(
        droneTelemetry.latitude.trim() &&
          droneTelemetry.longitude.trim() &&
          droneTelemetry.altitudeM.trim(),
      )
      const metadata = {
        runwayId: effectiveRunwayId,
        ...(hasDroneTelemetry
          ? {
              droneLatitude: droneTelemetry.latitude.trim(),
              droneLongitude: droneTelemetry.longitude.trim(),
              droneAltitudeM: droneTelemetry.altitudeM.trim(),
            }
          : {}),
      }

      // A telemetry file is sent for videos, single images, and folder-as-video
      // sequences. In angle-sweep folder mode each image carries its own EXIF GPS,
      // so applying one telemetry file would collapse the whole sweep onto one fix.
      const telemetryFile = metadataFileForAnalysis(media.type, currentFolderMode, metadataFile)

      if (media.type === 'video') {
        setAnalysisProgress(copy.live.uploadingVideo)
        const result = await analyzeMedia(media.file, metadata, telemetryFile)
        rawResults = [result]
        frameContexts.push({
          frameLabel: `${result.frame_count ?? 0} labeled frames`,
          totalFrames: 1,
        })
      } else if (shouldAnalyzeFolderAsSequence(media.type, currentFolderMode)) {
        const files = media.files ?? []
        if (!files.length) {
          throw new Error(copy.live.noFolderImages)
        }
        if (files.length > MAX_BATCH_FRAMES) {
          throw new Error(
            copy.live.tooManyImages.replace('{count}', files.length).replace('{max}', MAX_BATCH_FRAMES),
          )
        }
        setAnalysisProgress(copy.live.uploadingSequence.replace('{count}', files.length))
        const result = await analyzeSequence(files, metadata, telemetryFile)
        rawResults = [result]
        frameContexts.push({
          frameLabel: `${result.frame_count ?? files.length} sequenced frames`,
          totalFrames: 1,
        })
      } else {
        // Image OR geotagged folder: analyze each image individually so every frame
        // carries its OWN GPS-derived viewing angle. A folder of geotagged images is
        // a descent sweep — per-image analysis is what powers the per-lamp
        // angle-vs-state charts and each lamp's detected red->white transition angle
        // (a single sequenced video would collapse to one angle for the whole clip).
        const frames =
          media.type === 'folder'
            ? (media.files ?? []).map((file) => ({ file, label: fileDisplayPath(file) }))
            : await extractFrameImages(media.file)
        if (!frames.length) {
          throw new Error(copy.live.noFolderImages)
        }
        if (frames.length > MAX_BATCH_FRAMES) {
          throw new Error(
            copy.live.tooManyImages.replace('{count}', frames.length).replace('{max}', MAX_BATCH_FRAMES),
          )
        }
        let bestScore = -1

        for (const [index, frame] of frames.entries()) {
          // A newer upload bumped runIdRef while we were mid-loop — stop now so a
          // superseded run can't keep pushing stale progress (or further analyze
          // calls) onto the media the user replaced.
          if (runIdRef.current !== runId) {
            return
          }
          setAnalysisProgress(copy.live.analyzingFrame.replace('{current}', index + 1).replace('{total}', frames.length))
          const result = await analyzeFrame(frame.file, metadata, telemetryFile)
          rawResults.push(result)
          frameContexts.push({
            frameLabel: frame.label,
            totalFrames: frames.length,
          })
          const score = result.global_state === 'unknown' ? result.confidence : result.confidence + 1
          if (score >= bestScore) {
            bestScore = score
            bestIndex = index
          }
        }
      }

      if (!rawResults.length) {
        throw new Error(copy.live.noMediaAnalyzed)
      }

      const resolvedArtifacts = await resolveResultArtifactUrls(rawResults, runId)
      if (resolvedArtifacts == null) {
        return
      }

      const scenarios = rawResults.map((result, index) =>
        scenarioFromBackendResult(result, {
          ...(frameContexts[index] ?? { frameLabel: 'Result', totalFrames: rawResults.length }),
          artifactUrl: resolvedArtifacts.urls[index],
        }),
      )
      bestScenario = scenarios[bestIndex] ?? scenarios[0] ?? null

      if (!bestScenario) {
        resolvedArtifacts.createdUrls.forEach(revokeMediaUrl)
        throw new Error(copy.live.noMediaAnalyzed)
      }

      // A newer upload replaced the media while this run was in flight — discard
      // this now-stale result rather than applying it to the new media.
      if (runIdRef.current !== runId) {
        resolvedArtifacts.createdUrls.forEach(revokeMediaUrl)
        return
      }

      clearResolvedArtifactUrls()
      resolvedArtifactUrlsRef.current = resolvedArtifacts.createdUrls
      // Keep every per-image scenario (in upload order) for still-image and
      // angle-sweep folder runs so the frame-history panel can drive navigation.
      // Videos and folder-as-video sequences collapse to one tracked payload.
      const nextBackendFrames = keepsFrameScenarios ? scenarios : []

      setBackendFrames(nextBackendFrames)
      setBackendResults(rawResults)
      setBackendFrameIndex(0)
      setBackendScenario(bestScenario)
      setActiveId('backend')
      setMedia((current) =>
        current
          ? {
              ...current,
              annotatedUrl: bestScenario.artifactUrl,
              annotatedType: bestScenario.artifactType,
            }
          : current,
      )
      // Clear the in-progress banner once the result is on screen (audit F21).
      // A lingering "Analysis complete" message would persist under the heading
      // with nothing left to report; the rendered result is the success signal.
      setAnalysisProgress('')
      // Non-blocking confirmation — the inline result panel is the primary
      // signal, the toast just confirms it from any scroll position / route.
      toast.success(copy.live.analysisComplete)
    } catch (error) {
      // Ignore a superseded run's error so a stale failure can't overwrite the
      // state for the media the user has selected now.
      if (runIdRef.current !== runId) {
        return
      }
      setAnalysisError(error.message)
      setAnalysisProgress('')
      toast.error(error.message)
    } finally {
      if (runIdRef.current === runId) {
        setIsAnalyzing(false)
      }
    }
  }

  return {
    activeId,
    media,
    folderMode,
    setFolderMode,
    runways,
    // Expose the reconciled id so the selector value, the active-card highlight and
    // the analyze call all agree even when the raw stored id is stale.
    selectedRunwayId: effectiveRunwayId,
    selectedRunway,
    setSelectedRunwayId,
    addRunway,
    removeRunway,
    refetchRunways,
    droneTelemetry,
    setDroneTelemetry,
    metadataFile,
    setMetadataFile,
    isAnalyzing,
    isExporting,
    exportError,
    setExportError,
    backendScenario,
    backendFrames,
    backendResults,
    backendFrameIndex,
    folderVideo,
    isTransformingFolderVideo,
    analysisError,
    analysisProgress,
    insightsRef,
    handleMediaFiles,
    handleMediaChange,
    selectBackendFrame,
    handleDownloadCharts,
    runBackendInference,
    transformFolderToVideo,
  }
}
