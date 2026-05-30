import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { Globe, Moon, Sun } from 'lucide-react'
import { Toaster, toast } from 'sonner'
import clsx from 'clsx'
import './App.css'
import {
  analyzeFrame,
  analyzeFrames,
  analyzeMedia,
  fetchReady,
} from './lib/api'
import { extractFrameImages } from './lib/frameExtraction'
import { loadPlotlyBundle } from './lib/plotlyBundle'
import { isImageFile, isVideoFile, fileDisplayPath } from './lib/fileType'
import { scenarioFromBackendResult } from './lib/papi'
import {
  STORAGE_KEYS,
  initialLanguage,
  initialTheme,
  safeLocalStorageSet,
} from './lib/storage'
import { stateCatalog } from './catalog/stateCatalog'
import { scenarios } from './catalog/scenarios'
import { LANGUAGE_LABELS, translations } from './i18n/translations'
import { translateScenario, translateState } from './i18n/translate'
import { useClickOutside } from './hooks/useClickOutside'
import { AppFooter } from './components/AppFooter'
import { IntroductionPage } from './pages/IntroductionPage'
import { LiveDemoPage } from './pages/LiveDemoPage'
import { InsightsPage } from './pages/InsightsPage'
import { HistoryPage } from './pages/HistoryPage'

const LANGUAGE_OPTIONS = ['en', 'de', 'nl', 'fr']

// Real UTC wall clock (hh:mm:ss) for the topbar util cluster — no fabricated
// value, just the browser's current time rendered in UTC with a 1s tick.
function formatUtcClock() {
  return new Date().toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'UTC',
    hour12: false,
  })
}

// Real minimal 404 (audit F01): replaces the old catch-all that silently
// rendered Introduction. Copy comes from i18n; the only literal is the mono
// '404' glyph.
function NotFound({ copy }) {
  return (
    <section className="not-found">
      <p className="not-found__code mono">404</p>
      <h1 className="not-found__title">{copy.notFound.title}</h1>
      <p className="not-found__message">{copy.notFound.message}</p>
      <Link className="cta-button" to="/">
        {copy.notFound.home}
      </Link>
    </section>
  )
}

function App() {
  const [theme, setTheme] = useState(initialTheme)
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
  const [language, setLanguage] = useState(initialLanguage)
  const [languageMenuOpen, setLanguageMenuOpen] = useState(false)
  const [backendStatus, setBackendStatus] = useState('checking')
  const [clock, setClock] = useState(() => formatUtcClock())
  const languageMenuRef = useRef(null)
  const languageTriggerRef = useRef(null)
  const languageOptionRefs = useRef([])

  const closeLanguageMenu = useCallback(() => setLanguageMenuOpen(false), [])
  useClickOutside(languageMenuRef, closeLanguageMenu, languageMenuOpen)
  const insightsRef = useRef(null)
  const copy = translations[language]

  const activeScenarioRaw = useMemo(
    () => {
      if (activeId === 'backend' && backendScenario) {
        return backendScenario
      }
      return scenarios.find((scenario) => scenario.id === activeId) ?? scenarios[0]
    },
    [activeId, backendScenario],
  )

  const activeScenario = useMemo(
    () => translateScenario(activeScenarioRaw, copy),
    [activeScenarioRaw, copy],
  )

  const activeState = useMemo(
    () =>
      translateState(
        stateCatalog.find((state) => state.id === activeScenario.stateId) ?? stateCatalog[stateCatalog.length - 1],
        copy,
      ),
    [activeScenario, copy],
  )

  const plotTheme = useMemo(
    () =>
      theme === 'dark'
        ? {
            paper: 'rgba(0,0,0,0)',
            plot: 'rgba(255,255,255,0.04)',
            text: '#dbe6f2',
            strong: '#ffffff',
            muted: '#9cb0c4',
            grid: 'rgba(219, 230, 242, 0.16)',
            border: 'rgba(219, 230, 242, 0.18)',
            // Navy/grey bar palette for the decision plot + ribbon chrome.
            accent: '#6fb4e6',
            accentSoft: 'rgba(111, 180, 230, 0.22)',
            track: 'rgba(219, 230, 242, 0.16)',
          }
        : {
            paper: 'rgba(0,0,0,0)',
            plot: 'rgba(25,42,61,0.035)',
            text: '#192a3d',
            strong: '#0c1d2d',
            muted: '#5a6b7d',
            grid: 'rgba(25, 42, 61, 0.16)',
            border: 'rgba(25, 42, 61, 0.18)',
            accent: '#00426e',
            accentSoft: 'rgba(0, 66, 110, 0.18)',
            track: 'rgba(25, 42, 61, 0.12)',
          },
    [theme],
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    // Persist so the choice survives a page reload (regression
    // FE-MOD-CRIT-3 / papi-user-test-2026-05-28). Wrapped in try/catch
    // because some browsers (Safari private mode) throw on setItem.
    safeLocalStorageSet(STORAGE_KEYS.theme, theme)
  }, [theme])

  useEffect(() => {
    safeLocalStorageSet(STORAGE_KEYS.language, language)
  }, [language])

  // Backend status badge (audit F17 / IMP-FE-17): probe the real readiness
  // endpoint on mount and every ~20s. fetchReady never throws — it returns
  // { ok: false } when the backend is down — so a probe failure just flips
  // the dot to "offline" instead of crashing the shell.
  useEffect(() => {
    let active = true

    async function probe() {
      const result = await fetchReady()
      if (active) {
        setBackendStatus(result.ok ? 'online' : 'offline')
      }
    }

    probe()
    const intervalId = window.setInterval(probe, 20_000)
    return () => {
      active = false
      window.clearInterval(intervalId)
    }
  }, [])

  // Live UTC clock cell — tick once a second. Real value only (audit: no
  // fabricated session/build timestamps).
  useEffect(() => {
    const intervalId = window.setInterval(() => setClock(formatUtcClock()), 1000)
    return () => window.clearInterval(intervalId)
  }, [])

  // When the language menu opens, move focus into the checked option so the
  // arrow keys (F24) have a starting point and keyboard users aren't stranded
  // on the trigger.
  useEffect(() => {
    if (!languageMenuOpen) {
      return
    }
    const checkedIndex = Math.max(0, LANGUAGE_OPTIONS.indexOf(language))
    languageOptionRefs.current[checkedIndex]?.focus()
  }, [languageMenuOpen, language])

  // Language menu keyboard support (audit F24): Escape closes and returns focus
  // to the trigger; ArrowUp/ArrowDown roves focus between the menuitemradio
  // options (wrapping); Home/End jump to the ends.
  const handleLanguageMenuKeyDown = useCallback(
    (event) => {
      const { key } = event
      if (key === 'Escape') {
        event.preventDefault()
        setLanguageMenuOpen(false)
        languageTriggerRef.current?.focus()
        return
      }

      const lastIndex = LANGUAGE_OPTIONS.length - 1
      const currentIndex = languageOptionRefs.current.indexOf(event.target)
      let nextIndex = null

      if (key === 'ArrowDown') {
        nextIndex = currentIndex >= lastIndex ? 0 : currentIndex + 1
      } else if (key === 'ArrowUp') {
        nextIndex = currentIndex <= 0 ? lastIndex : currentIndex - 1
      } else if (key === 'Home') {
        nextIndex = 0
      } else if (key === 'End') {
        nextIndex = lastIndex
      }

      if (nextIndex !== null) {
        event.preventDefault()
        languageOptionRefs.current[nextIndex]?.focus()
      }
    },
    [],
  )

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
      setAnalysisError(
        `Unsupported file: ${file.name}. Upload an image or video file.`,
      )
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
          throw new Error('No images were found in the selected folder.')
        }

        setAnalysisProgress(`Uploading ${folderImages.length} folder images to backend analysis`)
        const batch = await analyzeFrames(folderImages)
        rawResults = batch.results
        nextBackendFrames = batch.results.map((result, index) =>
          scenarioFromBackendResult(result, {
            frameLabel: `Frame ${index + 1}`,
            totalFrames: batch.results.length,
          }),
        )
        bestScenario = nextBackendFrames[0]
      } else if (media.type === 'video') {
        setAnalysisProgress('Uploading video to backend video analysis')
        const result = await analyzeMedia(media.file)
        rawResults = [result]
        bestScenario = scenarioFromBackendResult(result, {
          frameLabel: `${result.frame_count ?? 0} labeled frames`,
          totalFrames: 1,
        })
      } else {
        setAnalysisProgress('Extracting frames')
        const frames = await extractFrameImages(media.file)
        let bestScore = -1

        for (const [index, frame] of frames.entries()) {
          setAnalysisProgress(`Analyzing frame ${index + 1}/${frames.length}`)
          const result = await analyzeFrame(frame.file)
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
        throw new Error('No media was analyzed.')
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
      setAnalysisError(error.message)
      setAnalysisProgress('')
      toast.error(error.message)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const navItems = [
    { to: '/', label: copy.nav.introduction, end: true },
    { to: '/live-demo', label: copy.nav.liveDemo },
    { to: '/insights', label: copy.nav.insights },
    { to: '/history', label: copy.nav.history },
  ]

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {copy.a11y.skipToContent}
      </a>

      <header className="topbar">
        <Link className="brand" to="/" aria-label="PAPI Vision dashboard">
          <span className="brand-logo" aria-hidden="true">
            <img
              className="logo-light"
              src="/intersoft-electronics-logo.svg"
              alt=""
            />
            <img
              className="logo-dark"
              src="/intersoft-electronics-logo-white-inverse.svg"
              alt=""
            />
          </span>
          <span className="brand-text">
            <strong>PAPI Vision</strong>
            <small>{copy.brand.subtitle}</small>
            <small className="brand-company">{copy.brand.company}</small>
          </span>
        </Link>

        <nav className="topnav" aria-label="Primary">
          {navItems.map((item, index) => (
            <NavLink
              key={item.to}
              className={({ isActive }) => clsx('nav-link', isActive && 'active')}
              to={item.to}
              end={item.end}
            >
              <span className="nav-link__idx mono" aria-hidden="true">
                {String(index + 1).padStart(2, '0')}
              </span>
              <span className="nav-link__label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="topbar-actions">
          <div className="util-cell status-cell" aria-live="polite">
            <span className={clsx('status-dot', `status-dot--${backendStatus}`)} aria-hidden="true" />
            <span className="util-cell__value mono">{copy.status[backendStatus]}</span>
          </div>
          <div className="util-cell">
            <span className="util-cell__label mono">Site</span>
            <span className="util-cell__value mono">EDNY</span>
          </div>
          <div className="util-cell clock-cell">
            <span className="util-cell__value mono tnum" aria-hidden="true">{clock}</span>
            <span className="util-cell__label mono">UTC</span>
          </div>
          <div className="language-switch topbar-control" ref={languageMenuRef}>
            <button
              className="language-trigger"
              type="button"
              ref={languageTriggerRef}
              onClick={() => setLanguageMenuOpen((current) => !current)}
              aria-expanded={languageMenuOpen}
              aria-haspopup="menu"
              aria-label="Choose language"
            >
              <Globe size={18} />
              <span>{language.toUpperCase()}</span>
            </button>
            {languageMenuOpen && (
              <div
                className="language-menu"
                role="menu"
                aria-label="Language"
                tabIndex={-1}
                onKeyDown={handleLanguageMenuKeyDown}
              >
                {LANGUAGE_OPTIONS.map((option, index) => (
                  <button
                    className={clsx(option === language && 'active')}
                    key={option}
                    type="button"
                    role="menuitemradio"
                    aria-checked={option === language}
                    ref={(node) => {
                      languageOptionRefs.current[index] = node
                    }}
                    onClick={() => {
                      setLanguage(option)
                      // Drop any stale PDF-export banner so it never lingers in
                      // the previous language.
                      setExportError('')
                      setLanguageMenuOpen(false)
                      languageTriggerRef.current?.focus()
                    }}
                  >
                    <span>{option.toUpperCase()}</span>
                    <small>{LANGUAGE_LABELS[option]}</small>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="topbar-control">
            <button
              className="icon-button"
              type="button"
              onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </div>
        </div>
      </header>

      <main id="main-content">
        <Routes>
        <Route path="/" element={<IntroductionPage copy={copy} />} />
        <Route
          path="/live-demo"
          element={
            <LiveDemoPage
              activeScenario={activeScenario}
              activeState={activeState}
              isAnalyzing={isAnalyzing}
              media={media}
              backendScenario={backendScenario}
              backendFrames={backendFrames}
              backendFrameIndex={backendFrameIndex}
              analysisError={analysisError}
              analysisProgress={analysisProgress}
              handleMediaFiles={handleMediaFiles}
              runBackendInference={runBackendInference}
              selectBackendFrame={selectBackendFrame}
              handleMediaChange={handleMediaChange}
              copy={copy}
            />
          }
        />
        <Route
          path="/insights"
          element={
            <InsightsPage
              activeScenario={activeScenario}
              backendResults={backendResults}
              plotTheme={plotTheme}
              insightsRef={insightsRef}
              isExporting={isExporting}
              exportError={exportError}
              onDownloadCharts={handleDownloadCharts}
              copy={copy}
            />
          }
        />
        <Route path="/history" element={<HistoryPage copy={copy} />} />
        <Route path="/demo" element={<Navigate to="/live-demo" replace />} />
        <Route path="*" element={<NotFound copy={copy} />} />
        </Routes>
      </main>

      <AppFooter copy={copy} />

      {/* Toasts supplement — never replace — the inline status/error banners,
          so a critical failure is still visible in page context. Theme tracks
          the app theme so light/dark stay consistent. */}
      <Toaster
        theme={theme}
        position="bottom-right"
        toastOptions={{ className: 'papi-toast' }}
      />
    </div>
  )
}

export default App
