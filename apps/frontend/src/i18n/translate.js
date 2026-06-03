import { translations } from './translations'

export function translateState(state, copy) {
  const translated = copy.states[state.id]
  if (!translated) {
    return state
  }
  return { ...state, label: translated[0], description: translated[1] }
}

export function translateScenario(scenario, copy) {
  const translated = copy.scenarios[scenario.id]
  if (!translated) {
    return scenario
  }
  return {
    ...scenario,
    label: translated[0],
    badge: scenario.id === 'backend' && scenario.logId ? scenario.badge : translated[1],
    summary: translated[2] ?? scenario.summary,
    condition: translated[3] ?? scenario.condition,
    angle: scenario.angle === translations.en.live.angleUnavailable ? copy.live.angleUnavailable : scenario.angle,
    angleSummary: translateAngleSummary(scenario.angleSummary, copy),
  }
}

// Localize the angle provenance label. When unavailable, the source slot carries the
// "missing metadata" message; when available, the backend enum (request_metadata,
// file_metadata, telemetry_file, metadata) is mapped to a human-readable, localized
// string, falling back to the raw value if the locale has no entry.
function translateAngleSummary(angleSummary, copy) {
  if (!angleSummary) {
    return angleSummary
  }
  if (!angleSummary.available) {
    return { ...angleSummary, source: copy.live.missingMetadata }
  }
  return {
    ...angleSummary,
    source: copy.live.angleSource?.[angleSummary.source] ?? angleSummary.source,
  }
}
