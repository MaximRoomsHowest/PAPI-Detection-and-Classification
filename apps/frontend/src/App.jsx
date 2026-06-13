import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import './App.css'
import {
  STORAGE_KEYS,
  initialLanguage,
  initialTheme,
  safeLocalStorageSet,
} from './lib/storage'
import { translations } from './i18n/translations'
import { Topbar } from './components/Topbar'
import { AppFooter } from './components/AppFooter'
import { ErrorBoundary } from './components/ErrorBoundary'
import { CookieConsent } from './components/CookieConsent'
import { LiveDemoProvider } from './context/LiveDemoProvider'
import { IntroductionPage } from './pages/IntroductionPage'
import { LiveDemoPage } from './pages/LiveDemoPage'
import { InsightsPage } from './pages/InsightsPage'
import { HistoryPage } from './pages/HistoryPage'
import { RunwaysPage } from './pages/RunwaysPage'

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

function wasBrowserReload() {
  const navigation = performance.getEntriesByType?.('navigation')?.[0]
  if (navigation?.type) {
    return navigation.type === 'reload'
  }
  return performance.navigation?.type === performance.navigation?.TYPE_RELOAD
}

function RouteEffects() {
  const location = useLocation()
  const navigate = useNavigate()
  const [shouldResetReloadPath] = useState(wasBrowserReload)
  const reloadResetHandledRef = useRef(false)

  useEffect(() => {
    if (shouldResetReloadPath && !reloadResetHandledRef.current) {
      reloadResetHandledRef.current = true
      if (location.pathname !== '/') {
        navigate('/', { replace: true })
        return
      }
    }

    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [location.pathname, navigate, shouldResetReloadPath])

  return null
}

function App() {
  const [theme, setTheme] = useState(initialTheme)
  const [language, setLanguage] = useState(initialLanguage)
  const copy = translations[language]

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
    // Keep <html lang> in sync so screen readers switch voices with the UI and
    // locale-aware CSS/formatting sees the active language (index.html ships
    // lang="en" statically).
    document.documentElement.lang = language
  }, [language])

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {copy.a11y.skipToContent}
      </a>

      <RouteEffects />

      <Topbar
        copy={copy}
        theme={theme}
        onToggleTheme={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
        language={language}
        onSelectLanguage={setLanguage}
      />

      <main id="main-content">
        {/* Route-level boundary: a render crash in any single page is caught here
            so the shell (Topbar / Footer / Toaster) survives and shows a
            recover-by-reload fallback in place of the routed view, instead of
            the whole app blanking. Complements the top-level boundary in main.jsx. */}
        <ErrorBoundary>
          {/* Runway state (list + active selection + add/delete) plus the Live
              Demo analysis state are shared app-wide through this one provider, so
              the Runways page and the Live Demo runway selector stay in sync. Only
              the route matched by react-router mounts, so the value still drives a
              single page at a time. The provider owns useAnalysis() itself, so
              analysis state changes (e.g. per-frame progress ticks) re-render its
              consumers — not App or this shell. */}
          <LiveDemoProvider copy={copy}>
            <Routes>
              <Route path="/" element={<IntroductionPage copy={copy} />} />
              <Route path="/live-demo" element={<LiveDemoPage copy={copy} plotTheme={plotTheme} />} />
              <Route path="/runways" element={<RunwaysPage copy={copy} />} />
              <Route path="/insights" element={<InsightsPage copy={copy} plotTheme={plotTheme} />} />
              <Route path="/history" element={<HistoryPage copy={copy} />} />
              <Route path="/demo" element={<Navigate to="/live-demo" replace />} />
              <Route path="*" element={<NotFound copy={copy} />} />
            </Routes>
          </LiveDemoProvider>
        </ErrorBoundary>
      </main>

      <AppFooter copy={copy} />

      <CookieConsent copy={copy} />

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
