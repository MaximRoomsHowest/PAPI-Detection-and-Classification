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
    angleSummary:
      scenario.angleSummary && !scenario.angleSummary.available
        ? {
            ...scenario.angleSummary,
            source: copy.live.missingMetadata,
          }
        : scenario.angleSummary,
  }
}
