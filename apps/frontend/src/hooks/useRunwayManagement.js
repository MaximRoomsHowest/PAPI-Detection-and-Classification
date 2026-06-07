import { useEffect, useMemo, useState } from 'react'
import { createRunway, deleteRunway as deleteRunwayRequest, fetchRunways } from '../lib/api'
import { useFetch } from './useFetch'
import { resolveRunwayId } from '../lib/runwaySelection'
import { STORAGE_KEYS, safeLocalStorageSet, initialRunwayId } from '../lib/storage'

// Runway list + selection, shared app-wide via the Live-Demo context so the Runways
// page and the Live Demo selector stay in sync. Self-contained except for the one
// value the analysis run needs: ``effectiveRunwayId`` (the reconciled selection),
// which the useAnalysis orchestrator threads into runBackendInference.
export function useRunwayManagement() {
  // Runway selection: the list comes from the backend (/api/runways); the chosen
  // id is sent as `runway_id` so the analysis scores against the right PAPI unit's
  // surveyed geometry. The id is persisted across reloads (localStorage) and
  // reconciled against the live list, so a stored/selected id that no longer exists
  // (custom runway deleted in another tab) self-heals to a safe default instead of
  // silently breaking the selector and the analyze call.
  const { data: runwayData, refetch: refetchRunways } = useFetch(fetchRunways, [])
  // Memoised so its identity is stable across renders — an inline `?? []` makes a
  // new array every render, which would churn the dependent memo/effect below.
  const runways = useMemo(() => runwayData ?? [], [runwayData])
  const [selectedRunwayId, setSelectedRunwayId] = useState(initialRunwayId)

  // Effective selection: the stored id reconciled against the live list. A
  // stale/deleted id (e.g. a custom runway removed in another tab) transparently
  // resolves to a safe default — DERIVED, not stored, so we never setState in an
  // effect (which cascades renders). Before the list loads we keep the raw id so the
  // persisted choice isn't clobbered by the empty-list fallback.
  const effectiveRunwayId =
    runways.length > 0 ? resolveRunwayId(selectedRunwayId, runways) : selectedRunwayId

  // Persist the effective id (best-effort; safe in private-mode / SSR) so a stale
  // stored id self-heals on disk too once the live list is known.
  useEffect(() => {
    safeLocalStorageSet(STORAGE_KEYS.runway, effectiveRunwayId)
  }, [effectiveRunwayId])

  // The full record for the selected runway, shared app-wide so the Live Demo and
  // Runways page can show its label + geometry (not just the id).
  const selectedRunway = useMemo(
    () => runways.find((runway) => runway.id === effectiveRunwayId) ?? null,
    [runways, effectiveRunwayId],
  )

  // Runway management, shared app-wide via context so the Runways page and the
  // Live Demo selector stay in sync. A newly added runway is persisted server-side
  // and immediately usable for analysis, so refetch the list and make it active;
  // deleting the active runway falls back to the backend default (papi_24).
  async function addRunway(payload) {
    const created = await createRunway(payload)
    refetchRunways()
    setSelectedRunwayId(created.id)
    return created
  }

  async function removeRunway(runwayId) {
    await deleteRunwayRequest(runwayId)
    refetchRunways()
    // Fall off the deleted runway to a still-valid one. papi_24 is a built-in
    // (undeletable), so resolveRunwayId always yields a valid id; the reconciliation
    // effect is the backstop once the refetched list arrives.
    setSelectedRunwayId((current) =>
      current === runwayId
        ? resolveRunwayId(null, runways.filter((runway) => runway.id !== runwayId))
        : current,
    )
  }

  return {
    runways,
    effectiveRunwayId,
    selectedRunway,
    setSelectedRunwayId,
    addRunway,
    removeRunway,
    refetchRunways,
  }
}
