import { useEffect, useRef } from 'react'
import { Cookie } from 'lucide-react'

// Storage-consent banner. Shows only while the visitor is undecided; the choice is
// persisted by useConsent so it never re-nags. It is honest and functional, not
// cosmetic: "Allow" lets the app remember theme/language/runway across visits,
// "Decline" keeps the session ephemeral (see setPreference / setConsentDecision).
export function CookieConsent({ copy, consent }) {
  const cardRef = useRef(null)
  const acceptRef = useRef(null)
  const c = copy.cookie

  // Move focus into the banner when it appears, and let Escape decline (necessary
  // only) so keyboard users aren't trapped having to find the buttons.
  useEffect(() => {
    if (consent.decided) return undefined
    acceptRef.current?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') consent.decline()
    }
    const node = cardRef.current
    node?.addEventListener('keydown', onKeyDown)
    return () => node?.removeEventListener('keydown', onKeyDown)
  }, [consent])

  if (consent.decided) {
    return null
  }

  return (
    <aside
      ref={cardRef}
      className="cookie-card"
      role="dialog"
      aria-labelledby="cookie-title"
      aria-describedby="cookie-message"
    >
      <span className="cookie-card__icon" aria-hidden="true">
        <Cookie size={28} />
      </span>
      <div>
        <h2 id="cookie-title">{c.title}</h2>
        <p id="cookie-message">{c.message}</p>
        <p className="cookie-card__detail">{c.detail}</p>
      </div>
      <div className="cookie-card__actions">
        <button ref={acceptRef} type="button" onClick={consent.accept}>
          {c.accept}
        </button>
        <button type="button" onClick={consent.decline}>
          {c.decline}
        </button>
      </div>
    </aside>
  )
}
