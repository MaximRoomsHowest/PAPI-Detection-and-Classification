import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Globe, Moon, Sun } from 'lucide-react'
import clsx from 'clsx'
import { LANGUAGE_LABELS } from '../i18n/translations'
import { useClickOutside } from '../hooks/useClickOutside'

const LANGUAGE_OPTIONS = ['en', 'de', 'nl', 'fr']

// Real UTC wall clock (hh:mm:ss) — no fabricated value, just the browser's
// current time rendered in UTC with a 1s tick.
function formatUtcClock() {
  return new Date().toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: 'UTC',
    hour12: false,
  })
}

// The sticky application header: brand, primary nav, backend-status dot, UTC
// clock, language menu and theme toggle. Extracted from App.jsx so the App
// component is just the route shell, and so the once-a-second clock tick
// re-renders only the topbar instead of the whole page tree.
export function Topbar({ copy, theme, onToggleTheme, language, onSelectLanguage, backendStatus }) {
  const [languageMenuOpen, setLanguageMenuOpen] = useState(false)
  const [clock, setClock] = useState(() => formatUtcClock())
  const languageMenuRef = useRef(null)
  const languageTriggerRef = useRef(null)
  const languageOptionRefs = useRef([])

  const closeLanguageMenu = useCallback(() => setLanguageMenuOpen(false), [])
  useClickOutside(languageMenuRef, closeLanguageMenu, languageMenuOpen)

  // Tick once a second. Keeping this state in the Topbar means the tick only
  // re-renders the header, not the entire application tree (audit frontend-perf).
  useEffect(() => {
    const intervalId = window.setInterval(() => setClock(formatUtcClock()), 1000)
    return () => window.clearInterval(intervalId)
  }, [])

  // When the menu opens, move focus into the checked option so the arrow keys
  // (F24) have a starting point and keyboard users aren't stranded on the trigger.
  useEffect(() => {
    if (!languageMenuOpen) {
      return
    }
    const checkedIndex = Math.max(0, LANGUAGE_OPTIONS.indexOf(language))
    languageOptionRefs.current[checkedIndex]?.focus()
  }, [languageMenuOpen, language])

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
  }, [])

  const navItems = [
    { to: '/', label: copy.nav.introduction, end: true },
    { to: '/live-demo', label: copy.nav.liveDemo },
    { to: '/insights', label: copy.nav.insights },
    { to: '/history', label: copy.nav.history },
  ]

  return (
    <header className="topbar">
      <Link className="brand" to="/" aria-label={copy.a11y.brandLabel}>
        <span className="brand-logo" aria-hidden="true">
          <img className="logo-light" src="/intersoft-electronics-logo.svg" alt="" />
          <img className="logo-dark" src="/intersoft-electronics-logo-white-inverse.svg" alt="" />
        </span>
        <span className="brand-text">
          <strong>PAPI Vision</strong>
          <small>{copy.brand.subtitle}</small>
          <small className="brand-company">{copy.brand.company}</small>
        </span>
      </Link>

      <nav className="topnav" aria-label={copy.a11y.primaryNav}>
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
            <Globe size={18} />
            <span>{language.toUpperCase()}</span>
          </button>
          {languageMenuOpen && (
            <div
              className="language-menu"
              role="menu"
              aria-label={copy.a11y.languageMenu}
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
                  tabIndex={option === language ? 0 : -1}
                  ref={(node) => {
                    languageOptionRefs.current[index] = node
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
            {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
          </button>
        </div>
      </div>
    </header>
  )
}
