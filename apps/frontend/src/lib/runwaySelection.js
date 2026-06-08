// Pure runway-selection helpers — no React, so they unit-test without rendering.

export const DEFAULT_RUNWAY_ID = 'papi_24'

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
  if (ids.includes(DEFAULT_RUNWAY_ID)) {
    return DEFAULT_RUNWAY_ID
  }
  return ids[0] ?? DEFAULT_RUNWAY_ID
}

export function runwayDisplayName(runwayId, runways) {
  const id = runwayId || DEFAULT_RUNWAY_ID
  const runway = Array.isArray(runways) ? runways.find((candidate) => candidate.id === id) : null
  return runway?.label || id
}

export function sessionRunwaySummary(results, runways) {
  const ids = []
  const seen = new Set()
  for (const result of Array.isArray(results) ? results : []) {
    const id = result?.runway_id
    if (!id || seen.has(id)) continue
    seen.add(id)
    ids.push(id)
  }

  if (ids.length === 0) {
    return { kind: 'none', ids, label: null }
  }

  if (ids.length === 1) {
    return { kind: 'single', ids, label: runwayDisplayName(ids[0], runways) }
  }

  return {
    kind: 'mixed',
    ids,
    label: ids.map((id) => runwayDisplayName(id, runways)).join(', '),
  }
}
