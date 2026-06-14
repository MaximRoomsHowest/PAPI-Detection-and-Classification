import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Globe, Moon, Sun } from 'lucide-react'
import clsx from 'clsx'
import { LANGUAGE_LABELS, SUPPORTED_LANGUAGES } from '../i18n/translations'
import { useClickOutside } from '../hooks/useClickOutside'
import { fetchHealth } from '../lib/api'
import { PapiGlyph } from './PapiGlyph'
import { AdminUnlock } from './AdminUnlock'

// Aviation operations run on UTC, and every History timestamp ultimately keys
// against backend (UTC) time — the clock cell makes that frame of reference
// visible. en-GB locale only fixes the 24h digit layout; digits are digits in
// all four UI languages.
const UTC_CLOCK = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC',
  hour12: false,
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

// Readiness poll cadence. Slow on purpose: the cell is a passive indicator,
// not a monitor — analysis calls surface their own errors.
const HEALTH_POLL_MS = 45_000

function useUtcClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])
  return UTC_CLOCK.format(now)
}

function useBackendStatus() {
  const [status, setStatus] = useState('checking')
  useEffect(() => {
    const controller = new AbortController()
    let timer = null
    const probe = async () => {
      const ok = await fetchHealth(controller.signal)
      if (controller.signal.aborted) return
      setStatus(ok ? 'online' : 'offline')
      timer = setTimeout(probe, HEALTH_POLL_MS)
    }
    probe()
    return () => {
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [])
  return status
}

// The sticky application header: brand, primary nav, live util cells (UTC
// clock + backend readiness) and the language / theme controls. Extracted from
// App.jsx so the App component stays as the route shell.
export function Topbar({ copy, theme, onToggleTheme, language, onSelectLanguage, admin }) {
  const [languageMenuOpen, setLanguageMenuOpen] = useState(false)
  const languageMenuRef = useRef(null)
  const languageTriggerRef = useRef(null)
  const utcTime = useUtcClock()
  const backendStatus = useBackendStatus()
  // Stable ref store keyed by the language code (not a render-time array index),
  // so the ref callback never mutates an array during render. Each option's
  // callback sets its own entry on mount and clears it on unmount. Initialised
  // lazily so the Map isn't rebuilt and discarded on every render.
  const languageOptionRefs = useRef(null)
  if (languageOptionRefs.current === null) {
    languageOptionRefs.current = new Map()
  }
  // Resolve an option's DOM node by its position in SUPPORTED_LANGUAGES. Reads only
  // the (stable) ref Map and the module-level option list, so it's safe to keep
  // referentially stable and list as a hook dependency.
  const optionNodeAt = useCallback(
    (index) => languageOptionRefs.current.get(SUPPORTED_LANGUAGES[index]) ?? null,
    [],
  )

  const closeLanguageMenu = useCallback(() => setLanguageMenuOpen(false), [])
  useClickOutside(languageMenuRef, closeLanguageMenu, languageMenuOpen)

  // When the menu opens, move focus into the checked option so the arrow keys
  // (F24) have a starting point and keyboard users aren't stranded on the trigger.
  useEffect(() => {
    if (!languageMenuOpen) {
      return
    }
    const checkedIndex = Math.max(0, SUPPORTED_LANGUAGES.indexOf(language))
    optionNodeAt(checkedIndex)?.focus()
  }, [languageMenuOpen, language, optionNodeAt])

  // Language menu keyboard support (audit F24): Escape closes and returns focus
  // to the trigger; ArrowUp/ArrowDown roves between the menuitemradio options
  // (wrapping); Home/End jump to the ends.
  const handleLanguageMenuKeyDown = useCallback((event) => {
    const { key } = event
    if (key === 'Escape') {
      event.preventDefault()
      setLanguageMenuOpen(false)
      languageTriggerRef.current?.focus()
      return
    }

    const lastIndex = SUPPORTED_LANGUAGES.length - 1
    const currentIndex = SUPPORTED_LANGUAGES.findIndex(
      (option) => languageOptionRefs.current.get(option) === event.target,
    )
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
      optionNodeAt(nextIndex)?.focus()
    }
  }, [optionNodeAt])

  const navItems = [
    { to: '/', label: copy.nav.introduction, end: true },
    { to: '/live-demo', label: copy.nav.liveDemo },
    { to: '/runways', label: copy.nav.runways },
    { to: '/insights', label: copy.nav.insights },
    { to: '/history', label: copy.nav.history },
    // Management routes appear only in admin mode so the public demo stays clean.
    ...(admin?.isAdmin
      ? [
          { to: '/models', label: copy.nav.models },
          { to: '/datasets', label: copy.nav.datasets },
        ]
      : []),
  ]

  return (
    <header className="topbar">
      <Link className="brand" to="/" aria-label={copy.a11y.brandLabel}>
        <PapiGlyph size="brand" />
        <span className="brand-text">
          <strong>PAPI Vision</strong>
          <small>{copy.brand.subtitle}</small>
        </span>
      </Link>

      <nav className="topnav" aria-label={copy.a11y.primaryNav}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to={item.to}
            end={item.end}
          >
            <span className="nav-link__label">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="topbar-actions">
        <div className="util-cell clock-cell" aria-hidden="true">
          <span className="util-cell__label">UTC</span>
          <span className="util-cell__value mono">{utcTime}</span>
        </div>
        <div className="util-cell status-cell">
          <span className={`status-dot status-dot--${backendStatus}`} aria-hidden="true" />
          <span className="util-cell__label">{copy.topbar.backend}</span>
          <span className="util-cell__value">{copy.status[backendStatus]}</span>
        </div>
        <div className="language-switch topbar-control" ref={languageMenuRef}>
          <button
            className="language-trigger"
            type="button"
            ref={languageTriggerRef}
            onClick={() => setLanguageMenuOpen((current) => !current)}
            onKeyDown={(event) => {
              // Escape from the trigger itself also closes the menu (the menu's
              // own handler only fires when focus is already inside it).
              if (event.key === 'Escape' && languageMenuOpen) {
                event.preventDefault()
                setLanguageMenuOpen(false)
              }
            }}
            aria-expanded={languageMenuOpen}
            aria-haspopup="menu"
            aria-label={copy.a11y.chooseLanguage}
          >
            <Globe size={16} />
            <span>{language.toUpperCase()}</span>
          </button>
          {languageMenuOpen && (
            <div
              className="language-menu"
              role="menu"
              aria-orientation="vertical"
              aria-label={copy.a11y.languageMenu}
              tabIndex={-1}
              onKeyDown={handleLanguageMenuKeyDown}
            >
              {SUPPORTED_LANGUAGES.map((option) => (
                <button
                  className={clsx(option === language && 'active')}
                  key={option}
                  type="button"
                  role="menuitemradio"
                  aria-checked={option === language}
                  tabIndex={option === language ? 0 : -1}
                  ref={(node) => {
                    if (node) {
                      languageOptionRefs.current.set(option, node)
                    } else {
                      languageOptionRefs.current.delete(option)
                    }
                  }}
                  onClick={() => {
                    onSelectLanguage(option)
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
            onClick={onToggleTheme}
            aria-label={theme === 'dark' ? copy.a11y.switchToLight : copy.a11y.switchToDark}
          >
            {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
        {admin ? <AdminUnlock admin={admin} copy={copy} /> : null}
      </div>
    </header>
  )
}
