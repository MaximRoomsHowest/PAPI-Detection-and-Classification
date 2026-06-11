import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  analyzeFrame,
  analyzeMedia,
  analyzeSequence,
  fetchModels,
  positiveNumberEnv,
  resolveMediaUrl,
  revokeMediaUrl,
} from '../lib/api'
import { localizedErrorMessage } from '../lib/errorMessages'
import { extractFrameImages } from '../lib/frameExtraction'
import { isImageFile, isVideoFile, fileDisplayPath } from '../lib/fileType'
import { scenarioFromBackendResult } from '../lib/papi'
import { createFolderVideo } from '../lib/folderVideo'
import {
  FOLDER_MODE_ANGLE_SWEEP,
  metadataFileForAnalysis,
  shouldAnalyzeFolderAsSequence,
  shouldKeepFrameScenarios,
} from '../lib/analysisMode'
import { useRunwayManagement } from './useRunwayManagement'
import { useChartExport } from './useChartExport'

// Client-side mirror of the backend PAPI_MAX_BATCH_FRAMES cap so an oversized folder is
// rejected up front instead of uploading the whole batch only to be 413'd (audit).
// positiveNumberEnv (api.js) also rejects negative/zero/NaN overrides, which a bare
// Number(...) || 200 would let through as a nonsensical cap.
const MAX_BATCH_FRAMES = positiveNumberEnv(import.meta.env.VITE_PAPI_MAX_BATCH_FRAMES, 200)

// Owns the Live-Demo upload + backend-inference state and the handlers that drive
// it — extracted from App.jsx so the App component is just the route shell. `copy`
// is the active-locale i18n object; every user-facing string is read from it.
//
// The two cleanly-separable concerns — runway management and the Insights PDF
// export — live in their own hooks (useRunwayManagement / useChartExport); this hook
// composes them and assembles the single flat object the Live-Demo context spreads.
// The media-upload + inference core stays here, deliberately NOT split further: it is
// tightly coupled through the shared `runIdRef` (stale-run guard, threaded across
// handleMediaFiles / resolveResultArtifactUrls / runBackendInference) and the one-shot
// auto-run effect, so separating it would only relocate that coupling into wiring.
export function useAnalysis(copy) {
  // Runway list + selection (shared with the Runways page). The reconciled
  // `effectiveRunwayId` is what the analyze calls score against.
  const {
    runways,
    runwayLoading,
    runwayError,
    effectiveRunwayId,
    selectedRunway,
    setSelectedRunwayId,
    addRunway,
    removeRunway,
    refetchRunways,
  } = useRunwayManagement()

  // Insights PDF export (independent of the analysis state).
  const { insightsRef, isExporting, exportError, setExportError, handleDownloadCharts } =
    useChartExport(copy)

  const [activeId, setActiveId] = useState('clean')
  const [media, setMedia] = useState(null)
  const [folderMode, setFolderMode] = useState(FOLDER_MODE_ANGLE_SWEEP)
  // The folder mode that PRODUCED the on-screen result. When the user flips the mode
  // toggle after a result is shown, this differs from `folderMode`, so the result is
  // flagged stale (re-run needed) instead of silently drifting from the toggle (audit P1).
  const [resultFolderMode, setResultFolderMode] = useState(null)

  // Optional manual drone telemetry for the elevation-angle calc, used when an
  // uploaded image carries no GPS EXIF (browser uploads usually strip it). Empty
  // strings mean "not provided": the backend then falls back to the file's EXIF,
  // then to angle-unavailable. Sent only when all three are present (the backend
  // requires lat + lon + altitude together).
  const [droneTelemetry, setDroneTelemetry] = useState({ latitude: '', longitude: '', altitudeM: '' })

  // Optional drone identifier persisted with every analysis (History/CSV
  // provenance: which aircraft flew the approach). An INPUT like the manual
  // telemetry — it survives media changes and travels with each run; empty
  // means "not provided" and the field is omitted (integration audit
  // 2026-06-11: the backend column existed but no UI could ever set it).
  const [droneId, setDroneId] = useState('')

  // Optional drone-telemetry FILE (DJI .SRT / CSV / JSON) paired with the upload.
  // Parsed server-side into drone fixes that take priority over the manual fields
  // and the media's embedded EXIF; for a video it powers the per-frame angle track
  // (the red->white sweep on Insights). Like the manual fields it is an INPUT, so it
  // persists across media changes — the user can pick the file before or after the
  // media and clears it explicitly.
  const [metadataFile, setMetadataFile] = useState(null)

  // Inference model selected from /api/models. The backend owns model availability and the
  // transition classifier's auto-"model" transition behavior; the UI sends only model_id so it
  // cannot drift into a conflicting model/method combination. Starts as null — NOT a guessed
  // registry id — so analyses fired before /api/models resolves (or after it fails, or against
  // a legacy backend with different ids) omit model_id and get the backend default instead of
  // 400ing on "Unknown model_id" (audit FE-1).
  const [selectedModelId, setSelectedModelIdState] = useState(null)
  const [modelOptions, setModelOptions] = useState([])
  const [modelOptionsLoading, setModelOptionsLoading] = useState(true)
  const [modelOptionsError, setModelOptionsError] = useState('')

  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [backendScenario, setBackendScenario] = useState(null)
  const [backendFrames, setBackendFrames] = useState([])
  // Raw AnalysisPayload[] kept in parallel with backendFrames so result-driven
  // views (crop/zoom, angle-vs-state, transition charts) read bbox/per-light
  // angles/transitions straight from the backend instead of the display scenario.
  const [backendResults, setBackendResults] = useState([])
  const [backendFrameIndex, setBackendFrameIndex] = useState(0)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisProgress, setAnalysisProgress] = useState('')
  // True when the numeric analysis succeeded but at least one annotated preview could not
  // be fetched — surfaced as an inline toolbar badge in addition to the toast (audit F6).
  const [artifactWarning, setArtifactWarning] = useState(false)
  const autoRunRequestedRef = useRef(false)
  const [folderVideo, setFolderVideo] = useState(null)
  const [isTransformingFolderVideo, setIsTransformingFolderVideo] = useState(false)
  // Monotonic analysis run id: bumped whenever new media is selected and captured
  // at the start of each run, so a slow in-flight analysis whose media was replaced
  // mid-flight discards its (now stale) result instead of painting it onto the new
  // upload (audit frontend-bugs: mid-analysis file swap).
  const runIdRef = useRef(0)
  const resolvedArtifactUrlsRef = useRef([])
  // AbortController for the in-flight analysis run. A newer run or a media swap aborts it
  // so the superseded backend request is genuinely CANCELLED (not just ignored client-side),
  // which prevents it finishing server-side and leaving a stale History row + artifact
  // (audit P2: stale backend requests can still create History rows/artifacts).
  const abortRef = useRef(null)

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

  useEffect(() => {
    let active = true
    fetchModels()
      .then((options) => {
        if (!active) return
        const list = Array.isArray(options) ? options : []
        setModelOptions(list)
        // Select the backend's default (or the first available) entry. An entry with
        // available:false is never auto-selected; when nothing is available the
        // selection stays null so model_id is omitted and the backend default applies.
        const fallback =
          list.find((model) => model.is_default && model.available !== false) ??
          list.find((model) => model.available !== false)
        setSelectedModelIdState((current) => {
          const stillAvailable = list.some(
            (model) => model.model_id === current && model.available !== false,
          )
          return stillAvailable ? current : fallback?.model_id ?? current
        })
      })
      .catch(() => {
        if (!active) return
        // api.js throws a typed code (MODEL_OPTIONS_ERROR_CODE) rather than a user-facing
        // string — every failure shape (HTTP error, timeout, malformed body) maps to the
        // active locale's message here, since this text renders in a live region (FE-4).
        setModelOptionsError(copy.live.modelLoadError)
      })
      .finally(() => {
        if (active) setModelOptionsLoading(false)
      })
    return () => {
      active = false
    }
    // copy is intentionally omitted: the registry fetch is mount-only and copy is read
    // solely to localize the failure message — re-fetching /api/models on every locale
    // switch would be wasted work for an unchanged registry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Cancel the in-flight analysis request (if any). Called when a newer run starts or the
  // user swaps media, so the superseded backend job is actually aborted instead of running
  // to completion and persisting a History row + artifact for a discarded result (audit P2).
  function abortInFlight() {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }

  async function resolveResultArtifactUrls(results, runId, signal) {
    const createdUrls = []
    const urls = []
    let failed = 0

    for (const result of results) {
      if (runIdRef.current !== runId) {
        createdUrls.forEach(revokeMediaUrl)
        return null
      }

      let url
      try {
        url = await resolveMediaUrl(result.artifact_url, signal)
      } catch {
        // A newer run aborted this fetch — discard quietly like the runId guard.
        if (signal?.aborted) {
          createdUrls.forEach(revokeMediaUrl)
          return null
        }
        // The numeric analysis already succeeded server-side; only the annotated preview
        // failed to load. Keep the result with no preview (artifactUrl=null) and let the
        // caller warn, instead of failing the whole analysis over a missing artifact —
        // which would hide a usable result (audit P2: artifact fetch failure hides analysis).
        failed += 1
        urls.push(null)
        continue
      }

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

    return { urls, createdUrls, failed }
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
      // Reject WITHOUT touching the current media or its result: the rejected
      // file never becomes the displayed media, so everything on screen still
      // belongs together and only the banner (which names the rejected file)
      // changes. The earlier behaviour (audit FB-03) cleared media + result to
      // avoid a stale panel "belonging" to the rejected file — but wiping a
      // finished sweep over one mis-dropped .txt costs the user their whole
      // analysis (user test 2026-06-11). Keeping media AND result is the
      // consistent variant of the same honesty rule.
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
    // newly selected media — and abort it so it doesn't finish server-side (audit P2).
    abortInFlight()
    runIdRef.current += 1
    clearResolvedArtifactUrls()
    setIsAnalyzing(false)
    setBackendScenario(null)
    setBackendFrames([])
    setBackendResults([])
    setBackendFrameIndex(0)
    clearFolderVideo()
    setArtifactWarning(false)
    setAnalysisError('')
    setAnalysisProgress('')
    autoRunRequestedRef.current = true

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

  function setSelectedModelId(nextModelId) {
    // Resolve functional updaters against the CURRENT state inside the updater — the
    // captured selectedModelId can be render-stale, which would both mis-resolve the
    // updater and let a duplicate id slip past the no-op guard (audit FE-5). Arming the
    // auto-run ref in here is idempotent, so a double-invoked updater stays harmless.
    setSelectedModelIdState((current) => {
      const next = typeof nextModelId === 'function' ? nextModelId(current) : nextModelId
      if (!next || next === current) {
        return current
      }
      if (media?.file) {
        autoRunRequestedRef.current = true
      }
      return next
    })
  }

  useEffect(() => {
    if (!autoRunRequestedRef.current || !media?.file || isAnalyzing) {
      return
    }

    // One-shot auto-run after a new upload commits. The request flag is a ref (not
    // state) so consuming it is not a setState-in-effect (eslint error) and adds no
    // render; the effect still fires because media?.file changed in the same handler
    // that set the flag. The flag is consumed INSIDE the timer callback, not here: an
    // unrelated re-render runs this effect's cleanup before the 0ms timer fires, and a
    // flag already cleared in the effect body would make the re-run of the effect see
    // "not armed" and silently cancel the queued run (audit FE-2). Left armed, the
    // re-run simply schedules a fresh timer.
    const timeoutId = window.setTimeout(() => {
      if (!autoRunRequestedRef.current) {
        return
      }
      autoRunRequestedRef.current = false
      runBackendInference()
    }, 0)

    return () => window.clearTimeout(timeoutId)
    // runBackendInference is intentionally omitted: it is re-created every render, so
    // listing it would re-run this effect on every render. The 0ms timer fires on the
    // next tick with an up-to-date closure, so there is no stale-closure risk.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [media?.file, isAnalyzing, selectedModelId])

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

    // Toggle OFF: a second activation returns to the per-frame view instead of
    // silently rebuilding the same video (user test 2026-06-11: the preview was
    // one-way — the frame navigator stayed visible but could not change what
    // the stage showed).
    if (folderVideo) {
      clearFolderVideo()
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

  async function runBackendInference() {
    if (!media?.file || isAnalyzing) {
      return
    }

    const runId = ++runIdRef.current
    // Abort any previous in-flight run, then open a fresh AbortController for THIS run so a
    // later run / media swap can cancel it server-side rather than just ignoring it (audit P2).
    abortInFlight()
    const controller = new AbortController()
    abortRef.current = controller
    const signal = controller.signal
    setIsAnalyzing(true)
    setAnalysisError('')
    setArtifactWarning(false)

    try {
      let bestScenario = null
      let bestIndex = 0
      let rawResults = []
      let partialFailures = 0
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
        modelId: selectedModelId,
        // appendMetadata (api.js) omits empty values, so an untouched field
        // never reaches the backend.
        droneId: droneId.trim(),
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
        const result = await analyzeMedia(media.file, metadata, telemetryFile, signal)
        rawResults = [result]
        frameContexts.push({
          frameLabel: copy.live.frameLabelLabeled.replace('{count}', String(result.frame_count ?? 0)),
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
        const result = await analyzeSequence(files, metadata, telemetryFile, signal)
        rawResults = [result]
        frameContexts.push({
          frameLabel: copy.live.frameLabelSequenced.replace('{count}', String(result.frame_count ?? files.length)),
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
          let result
          try {
            result = await analyzeFrame(frame.file, metadata, telemetryFile, signal)
          } catch (error) {
            // A newer run aborted us — bail to the outer catch (the runId guard drops it).
            if (signal.aborted) {
              throw error
            }
            // One frame failed mid-sweep — keep the frames that already succeeded instead
            // of discarding the whole batch, and warn afterwards (audit P2: partial failures
            // discard earlier successful frames).
            partialFailures += 1
            continue
          }
          rawResults.push(result)
          frameContexts.push({
            frameLabel: frame.label,
            totalFrames: frames.length,
          })
          const score = result.global_state === 'unknown' ? result.confidence : result.confidence + 1
          if (score >= bestScore) {
            bestScore = score
            // Index into rawResults (NOT the frame index): with failed frames skipped the
            // two diverge, and the `scenarios` array below is built from rawResults.
            bestIndex = rawResults.length - 1
          }
        }
      }

      if (!rawResults.length) {
        throw new Error(copy.live.noMediaAnalyzed)
      }

      const resolvedArtifacts = await resolveResultArtifactUrls(rawResults, runId, signal)
      if (resolvedArtifacts == null) {
        return
      }

      const scenarios = rawResults.map((result, index) =>
        scenarioFromBackendResult(result, {
          ...(frameContexts[index] ?? {
            frameLabel: copy.live.frameLabelResult,
            totalFrames: rawResults.length,
          }),
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
      // Remember which folder mode produced this result so the toggle can flag the result
      // stale if the user switches modes without re-running (audit P1).
      setResultFolderMode(currentFolderMode)
      // The index must point at the scenario being SHOWN (the best-scoring frame),
      // or the stage displays frame N while the navigator reads "1/x" and the
      // history panel highlights frame 0 — three views of one selection
      // disagreeing until the first manual navigation (user test 2026-06-11).
      // bestIndex indexes rawResults == scenarios == backendFrames (sweep mode).
      setBackendFrameIndex(keepsFrameScenarios ? bestIndex : 0)
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
      // Non-fatal warnings — the result is already on screen; these only explain a gap so
      // a partial sweep / missing preview isn't silently swallowed (audit P2).
      if (partialFailures > 0) {
        toast.warning(
          copy.live.partialFramesWarning
            .replace('{ok}', String(rawResults.length))
            .replace('{total}', String(rawResults.length + partialFailures))
            .replace('{failed}', String(partialFailures)),
        )
      }
      if (resolvedArtifacts.failed > 0) {
        setArtifactWarning(true)
        toast.warning(copy.live.artifactWarning)
      }
      // Non-blocking confirmation — the inline result panel is the primary
      // signal, the toast just confirms it from any scroll position / route.
      toast.success(copy.live.analysisComplete)
    } catch (error) {
      // Ignore a superseded run's error so a stale failure can't overwrite the
      // state for the media the user has selected now.
      if (runIdRef.current !== runId) {
        return
      }
      const message = localizedErrorMessage(error, copy)
      setAnalysisError(message)
      setAnalysisProgress('')
      toast.error(message)
    } finally {
      if (runIdRef.current === runId) {
        setIsAnalyzing(false)
      }
    }
  }

  // The on-screen folder result was produced in `resultFolderMode`; if the user has since
  // flipped the toggle, the result no longer matches the selected mode and needs a re-run
  // rather than silently drifting (audit P1: folder mode can drift from the displayed result).
  const folderResultStale =
    media?.type === 'folder' &&
    backendResults.length > 0 &&
    resultFolderMode != null &&
    resultFolderMode !== folderMode

  return {
    activeId,
    media,
    folderMode,
    setFolderMode,
    folderResultStale,
    runways,
    runwayLoading,
    runwayError,
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
    droneId,
    setDroneId,
    metadataFile,
    setMetadataFile,
    selectedModelId,
    setSelectedModelId,
    modelOptions,
    modelOptionsLoading,
    modelOptionsError,
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
    artifactWarning,
    insightsRef,
    handleMediaFiles,
    handleMediaChange,
    selectBackendFrame,
    handleDownloadCharts,
    runBackendInference,
    transformFolderToVideo,
  }
}
