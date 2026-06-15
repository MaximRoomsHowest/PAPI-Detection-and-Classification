import { useCallback, useState } from 'react'

// Legacy compatibility hook for older callers. The current cookie card is a
// friendly reload-visible welcome moment, not a persistence gate.
export function useConsent() {
  const [decision, setDecision] = useState(null)

  const accept = useCallback(() => setDecision('accepted'), [])

  const decline = useCallback(() => setDecision('declined'), [])

  const reopen = useCallback(() => setDecision(null), [])

  return { decision, decided: decision !== null, accept, decline, reopen }
}
