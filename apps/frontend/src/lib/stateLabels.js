import { backendStateId, stateCatalog } from '../catalog/stateCatalog'
import { translateState } from '../i18n/translate'

// Shared localization for raw backend enums. The Live Demo localizes
// global states via backendStateId -> stateCatalog -> copy.states and lamp
// colours via copy.status; History used to render the raw English values
// instead. Centralised here so every surface (chart hovers, History pills,
// filter options, the detail modal) reads the same localized label.

/**
 * Localized label for a backend global_state ("correct_glidepath", ...).
 * Unmapped raw values fall back to the localized status map, then a
 * prettified raw value — never a silent "Unknown".
 */
export function globalStateLabel(rawState, copy) {
  if (!rawState) return ''
  const id = backendStateId[rawState]
  if (id) {
    const entry = stateCatalog.find((state) => state.id === id)
    if (entry) return translateState(entry, copy).label
  }
  return copy.status?.[rawState] ?? rawState.replace(/_/g, ' ')
}

/**
 * Localized label for a backend lamp state ("white" | "red" | "transition" |
 * "obscured" | "occluded" | "unknown"), falling back to the raw value.
 */
export function lampStateLabel(rawState, copy) {
  if (!rawState) return ''
  return copy.status?.[rawState] ?? rawState
}
