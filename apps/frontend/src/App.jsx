import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import './App.css'
import { fetchReady } from './lib/api'
import {
  STORAGE_KEYS,
  initialLanguage,
  initialTheme,
  safeLocalStorageSet,
} from './lib/storage'
import { stateCatalog } from './catalog/stateCatalog'
import { scenarios } from './catalog/scenarios'
import { translations } from './i18n/translations'
import { translateScenario, translateState } from './i18n/translate'
import { useAnalysis } from './hooks/useAnalysis'
import { Topbar } from './components/Topbar'
import { AppFooter } from './components/AppFooter'
import { IntroductionPage } from './pages/IntroductionPage'
import { LiveDemoPage } from './pages/LiveDemoPage'
import { InsightsPage } from './pages/InsightsPage'
import { HistoryPage } from './pages/HistoryPage'

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
  const [language, setLanguage] = useState(initialLanguage)
  const [backendStatus, setBackendStatus] = useState('checking')
  const copy = translations[language]

  // Live-Demo upload + backend-inference state and handlers live in this hook
  // (extracted from App, which is now just the route shell + theme/language/status).
  const analysis = useAnalysis(copy)

  const activeScenarioRaw = useMemo(
    () => {
      if (analysis.activeId === 'backend' && analysis.backendScenario) {
        return analysis.backendScenario
      }
      return scenarios.find((scenario) => scenario.id === analysis.activeId) ?? scenarios[0]
    },
    [analysis.activeId, analysis.backendScenario],
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

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {copy.a11y.skipToContent}
      </a>

      <Topbar
        copy={copy}
        theme={theme}
        onToggleTheme={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
        language={language}
        onSelectLanguage={(option) => {
          setLanguage(option)
          // Drop any stale PDF-export banner so it never lingers in the previous language.
          analysis.setExportError('')
        }}
        backendStatus={backendStatus}
      />

      <main id="main-content">
        <Routes>
        <Route path="/" element={<IntroductionPage copy={copy} />} />
        <Route
          path="/live-demo"
          element={
            <LiveDemoPage
              activeScenario={activeScenario}
              activeState={activeState}
              isAnalyzing={analysis.isAnalyzing}
              media={analysis.media}
              runways={analysis.runways}
              selectedRunwayId={analysis.selectedRunwayId}
              onSelectRunway={analysis.setSelectedRunwayId}
              backendScenario={analysis.backendScenario}
              backendFrames={analysis.backendFrames}
              backendFrameIndex={analysis.backendFrameIndex}
              analysisError={analysis.analysisError}
              analysisProgress={analysis.analysisProgress}
              handleMediaFiles={analysis.handleMediaFiles}
              runBackendInference={analysis.runBackendInference}
              selectBackendFrame={analysis.selectBackendFrame}
              handleMediaChange={analysis.handleMediaChange}
              copy={copy}
            />
          }
        />
        <Route
          path="/insights"
          element={
            <InsightsPage
              backendResults={analysis.backendResults}
              plotTheme={plotTheme}
              insightsRef={analysis.insightsRef}
              isExporting={analysis.isExporting}
              exportError={analysis.exportError}
              onDownloadCharts={analysis.handleDownloadCharts}
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
