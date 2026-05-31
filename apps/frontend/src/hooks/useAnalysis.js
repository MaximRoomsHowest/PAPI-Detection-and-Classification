import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { analyzeFrame, analyzeFrames, analyzeMedia, fetchRunways } from '../lib/api'
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
  // Runway the live analysis runs against. EDNY has two PAPI units (papi_24 /
  // papi_06) and the angle/state solution depends on which one — the backend
  // accepts runway_id (default papi_24), so expose it as a Live-Demo selector
  // rather than hardwiring papi_24. Seeded with the two known runways so the
  // picker works even before (or without) the /api/runways fetch below.
  const [runways, setRunways] = useState([
    { id: 'papi_24', label: 'PAPI 24' },
    { id: 'papi_06', label: 'PAPI 06' },
  ])
  const [runwayId, setRunwayId] = useState('papi_24')

  useEffect(() => {
    return () => {
      if (media?.url) {
        URL.revokeObjectURL(media.url)
      }
    }
  }, [media?.url])

  // Load the real runway list once for the selector. Resilient by design — a
  // failed fetch keeps the seeded fallback instead of breaking the Live Demo.
  useEffect(() => {
    let active = true
    fetchRunways()
      .then((list) => {
        if (active && Array.isArray(list) && list.length) {
          setRunways(list.map((runway) => ({ id: runway.id, label: runway.label ?? runway.id })))
        }
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

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
      let nextBackendFrames = []
      // Raw payloads retained for the result-driven charts. For a folder every
      // image's payload is kept (one angle/state point per image); for a single
      // image or video it is the one aggregated payload.
      let rawResults = []

      if (media.type === 'folder') {
        const folderImages = media.files ?? []
        if (!folderImages.length) {
          throw new Error(copy.live.noFolderImages)
        }

        setAnalysisProgress(copy.live.uploadingFolder.replace('{count}', folderImages.length))
        const batch = await analyzeFrames(folderImages, { runwayId })
        rawResults = batch.results
        nextBackendFrames = batch.results.map((result, index) =>
          scenarioFromBackendResult(result, {
            frameLabel: `Frame ${index + 1}`,
            totalFrames: batch.results.length,
          }),
        )
        bestScenario = nextBackendFrames[0]
      } else if (media.type === 'video') {
        setAnalysisProgress(copy.live.uploadingVideo)
        const result = await analyzeMedia(media.file, { runwayId })
        rawResults = [result]
        bestScenario = scenarioFromBackendResult(result, {
          frameLabel: `${result.frame_count ?? 0} labeled frames`,
          totalFrames: 1,
        })
      } else {
        setAnalysisProgress(copy.live.extractingFrames)
        const frames = await extractFrameImages(media.file)
        let bestScore = -1

        for (const [index, frame] of frames.entries()) {
          setAnalysisProgress(copy.live.analyzingFrame.replace('{current}', index + 1).replace('{total}', frames.length))
          const result = await analyzeFrame(frame.file, { runwayId })
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
    runways,
    runwayId,
    setRunwayId,
  }
}
