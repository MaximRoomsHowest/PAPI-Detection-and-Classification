// Pure runway-selection helpers — no React, so they unit-test without rendering.

// Resolve a runway id against the live list. Returns the candidate when it still
// exists; else the backend default 'papi_24' (always a built-in, so it can never be
// deleted — a guaranteed-valid fallback); else the first runway in the list; else
// the default string as a last resort (empty list, shouldn't happen — built-ins are
// always present). This is what lets a stale/deleted persisted id self-heal to a
// valid selection instead of silently breaking the selector and the analyze call.
export function resolveRunwayId(candidateId, runways) {
  const ids = Array.isArray(runways) ? runways.map((runway) => runway.id) : []
  if (candidateId && ids.includes(candidateId)) {
    return candidateId
  }
  if (ids.includes('papi_24')) {
    return 'papi_24'
  }
  return ids[0] ?? 'papi_24'
}
