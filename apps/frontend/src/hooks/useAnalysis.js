import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  analyzeFrame,
  analyzeMedia,
  createRunway,
  deleteRunway as deleteRunwayRequest,
  fetchRunways,
} from '../lib/api'
import { useFetch } from './useFetch'
import { extractFrameImages } from '../lib/frameExtraction'
import { loadPlotlyBundle } from '../lib/plotlyBundle'
import { isImageFile, isVideoFile, fileDisplayPath } from '../lib/fileType'
import { scenarioFromBackendResult } from '../lib/papi'

// Owns the Live-Demo upload + backend-inference state and the handlers that drive
// it — extracted from App.jsx so the App component is just the route shell. `copy`
// is the active-locale i18n object; every user-facing string is read from it.
export function useAnalysis(copy) {
  const [activeId, setActiveId] = useState('clean')
  const [media, setMedia] = useState(null)
  // Runway selection: the list comes from the backend (/api/runways); the chosen
  // id is sent as `runway_id` so the analysis scores against the right PAPI unit's
  // surveyed geometry. Defaults to papi_24 to match the backend's own default.
  const { data: runwayData, refetch: refetchRunways } = useFetch(fetchRunways, [])
  const runways = runwayData ?? []
  const [selectedRunwayId, setSelectedRunwayId] = useState('papi_24')

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
    setSelectedRunwayId((current) => (current === runwayId ? 'papi_24' : current))
  }
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
  const insightsRef = useRef(null)
  // Monotonic analysis run id: bumped whenever new media is selected and captured
  // at the start of each run, so a slow in-flight analysis whose media was replaced
  // mid-flight discards its (now stale) result instead of painting it onto the new
  // upload (audit frontend-bugs: mid-analysis file swap).
  const runIdRef = useRef(0)

  useEffect(() => {
    return () => {
      if (media?.url) {
        URL.revokeObjectURL(media.url)
      }
    }
  }, [media?.url])

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
      setBackendScenario(null)
      setBackendFrames([])
      setBackendResults([])
      setBackendFrameIndex(0)
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
    setBackendScenario(null)
    setBackendFrames([])
    setBackendResults([])
    setBackendFrameIndex(0)
    setAnalysisError('')
    setAnalysisProgress('')

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

  function selectBackendFrame(index) {
    if (!backendFrames.length) {
      return
    }

    const nextIndex = Math.min(Math.max(index, 0), backendFrames.length - 1)
    setBackendFrameIndex(nextIndex)
    setBackendScenario(backendFrames[nextIndex])
    setActiveId('backend')
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
      // Per-image scenarios for the frame-history panel + FrameStage prev/next
      // nav. Stays empty for folders/videos, which collapse to a single
      // aggregated result (no per-frame stepping).
      const nextBackendFrames = []
      // Raw payloads retained for the result-driven charts. A folder is now
      // analysed as one sequenced video, so (like a video) it yields a single
      // aggregated payload; a single image yields its one payload.
      let rawResults = []
      // Telemetry sent with every analyze call. runway_id selects which PAPI
      // unit's geometry the backend scores + computes elevation angles against.
      const metadata = { runwayId: selectedRunwayId }

      if (media.type === 'video') {
        setAnalysisProgress(copy.live.uploadingVideo)
        const result = await analyzeMedia(media.file, metadata)
        rawResults = [result]
        bestScenario = scenarioFromBackendResult(result, {
          frameLabel: `${result.frame_count ?? 0} labeled frames`,
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
        let bestScore = -1

        for (const [index, frame] of frames.entries()) {
          // A newer upload bumped runIdRef while we were mid-loop — stop now so a
          // superseded run can't keep pushing stale progress (or further analyze
          // calls) onto the media the user replaced.
          if (runIdRef.current !== runId) {
            return
          }
          setAnalysisProgress(copy.live.analyzingFrame.replace('{current}', index + 1).replace('{total}', frames.length))
          const result = await analyzeFrame(frame.file, metadata)
          rawResults.push(result)
          const scenario = scenarioFromBackendResult(result, {
            frameLabel: frame.label,
            totalFrames: frames.length,
          })
          const score = result.global_state === 'unknown' ? result.confidence : result.confidence + 1
          if (score >= bestScore) {
            bestScore = score
            bestScenario = scenario
          }
          // Keep every per-image scenario (in upload order) so the frame-history
          // panel can list each frame's lamp state, angle, and confidence and let
          // the user step through them.
          nextBackendFrames.push(scenario)
        }
      }

      if (!bestScenario) {
        throw new Error(copy.live.noMediaAnalyzed)
      }

      // A newer upload replaced the media while this run was in flight — discard
      // this now-stale result rather than applying it to the new media.
      if (runIdRef.current !== runId) {
        return
      }

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
      setIsAnalyzing(false)
    }
  }

  return {
    activeId,
    media,
    runways,
    selectedRunwayId,
    setSelectedRunwayId,
    addRunway,
    removeRunway,
    refetchRunways,
    isAnalyzing,
    isExporting,
    exportError,
    setExportError,
    backendScenario,
    backendFrames,
    backendResults,
    backendFrameIndex,
    analysisError,
    analysisProgress,
    insightsRef,
    handleMediaFiles,
    handleMediaChange,
    selectBackendFrame,
    handleDownloadCharts,
    runBackendInference,
  }
}
