import { useEffect, useState } from 'react'
import { Cookie, Frown, Smile } from 'lucide-react'
import clsx from 'clsx'
import { STORAGE_KEYS, readStoredChoice, safeLocalStorageSet } from '../lib/storage'

export function CookieConsent({ copy }) {
  const [answer, setAnswer] = useState(null)
  // Persist the choice so the banner doesn't reappear on every reload. The lazy
  // initializer reads localStorage once at mount; a stored accepted/declined starts
  // the component dismissed, so it renders nothing (no banner flash) on return visits.
  const [dismissed, setDismissed] = useState(() =>
    Boolean(readStoredChoice(STORAGE_KEYS.cookie, ['accepted', 'declined'], null)),
  )
  const cookieCopy = copy.cookie ?? {
    title: 'Would you like a cookie?',
    message: 'A small welcome moment before you start exploring PAPI Vision.',
    accept: 'Yes, please',
    decline: 'No thanks',
    accepted: 'Enjoy the cookie',
    declined: 'Maybe next time',
  }

  useEffect(() => {
    if (!answer) {
      return undefined
    }

    const timeoutId = window.setTimeout(() => setDismissed(true), 1800)
    return () => window.clearTimeout(timeoutId)
  }, [answer])

  const respond = (value) => {
    safeLocalStorageSet(STORAGE_KEYS.cookie, value)
    setAnswer(value)
  }

  if (dismissed) {
    return null
  }

  if (answer) {
    return (
      <div className={clsx('cookie-toast', `cookie-toast--${answer}`)} role="status" aria-live="polite">
        <span className="cookie-toast__icon" aria-hidden="true">
          {answer === 'accepted' ? <Smile size={26} /> : <Frown size={26} />}
        </span>
        <strong>{answer === 'accepted' ? cookieCopy.accepted : cookieCopy.declined}</strong>
      </div>
    )
  }

  return (
    <aside className="cookie-card" aria-labelledby="cookie-title">
      <span className="cookie-card__icon" aria-hidden="true">
        <Cookie size={28} />
      </span>
      <div>
        <h2 id="cookie-title">{cookieCopy.title}</h2>
        <p>{cookieCopy.message}</p>
      </div>
      <div className="cookie-card__actions">
        <button type="button" onClick={() => respond('accepted')}>
          {cookieCopy.accept}
        </button>
        <button type="button" onClick={() => respond('declined')}>
          {cookieCopy.decline}
        </button>
      </div>
    </aside>
  )
}
