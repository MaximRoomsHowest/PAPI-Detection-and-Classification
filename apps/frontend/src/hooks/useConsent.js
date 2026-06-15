import { useCallback, useState } from 'react'
import { getConsentDecision, resetConsentDecision, setConsentDecision } from '../lib/storage'

// Storage-consent state for the whole app. `decision` is 'accepted' | 'declined' |
// null (undecided → the banner shows). `accept`/`decline` record the choice (so it
// never re-asks) and update local state so preference-persistence effects re-run;
// `reopen` clears it for the footer "Cookie preferences" control.
export function useConsent() {
  const [decision, setDecision] = useState(getConsentDecision)

  const accept = useCallback(() => {
    setConsentDecision('accepted')
    setDecision('accepted')
  }, [])

  const decline = useCallback(() => {
    setConsentDecision('declined')
    setDecision('declined')
  }, [])

  const reopen = useCallback(() => {
    resetConsentDecision()
    setDecision(null)
  }, [])

  return { decision, decided: decision !== null, accept, decline, reopen }
}
