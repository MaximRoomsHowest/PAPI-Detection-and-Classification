import { backendStateId, stateCatalog } from '../catalog/stateCatalog'
import { percent } from './format'
import { mediaUrl } from './api'

export function lampPattern(lamps) {
  const labels = lamps.map((lamp) => {
    if (lamp.state === 'white') {
      return 'white'
    }
    if (lamp.state === 'red') {
      return 'red'
    }
    if (lamp.state === 'transition') {
      return 'transition'
    }
    if (lamp.state === 'obscured') {
      return 'obscured'
    }
    return 'unknown'
  })
  return labels.join(' + ')
}

// `angleUnavailableLabel` is additive (defaults to the original English string)
// so existing callers and papi.test.js are unaffected, while a future caller can
// pass a localized label to remove the hardcoding from the rendered `condition`.
export function scenarioFromBackendResult(result, context, angleUnavailableLabel = 'Angle unavailable') {
  const stateId = backendStateId[result.global_state] ?? 'unknown'
  const activeState = stateCatalog.find((state) => state.id === stateId) ?? stateCatalog[stateCatalog.length - 1]
  const lamps = result.lamps.map((lamp) => ({
    id: lamp.index,
    status: lamp.state === 'unknown' ? 'occluded' : lamp.state,
    confidence: percent(lamp.confidence),
    bbox: lamp.bbox,
  }))
  // angle_available can be true while elevation_angle_deg is null (GPS present
  // but the angle solve failed), so guard the toFixed calls against null.
  const hasAngle = result.angle?.angle_available && result.angle.elevation_angle_deg != null
  const angle = hasAngle
    ? `${result.angle.elevation_angle_deg.toFixed(3)} deg`
    : angleUnavailableLabel
  const angleSummary = hasAngle
    ? {
        available: true,
        value: result.angle.elevation_angle_deg.toFixed(3),
        source: result.angle.angle_source ?? 'metadata',
        note: result.angle.angle_note,
      }
    : {
        available: false,
        value: 'N/A',
        source: 'missing metadata',
        note: result.angle?.angle_note ?? 'GPS/altitude metadata was not available.',
      }
  const latency = Math.max(0, Number(result.processing_ms) || 0)

  return {
    id: 'backend',
    label: 'Backend result',
    badge: result.log_id ? `log ${result.log_id.slice(0, 8)}` : 'live',
    stateId,
    summary: `${lampPattern(result.lamps)} = ${activeState.label.toLowerCase()}`,
    frame: context.totalFrames > 1 ? `${context.frameLabel} of ${context.totalFrames}` : context.frameLabel,
    condition: angle,
    lamps,
    metrics: {
      latency,
      boxConfidence: percent(result.confidence),
    },
    environmentClass: 'clear',
    artifactUrl: mediaUrl(result.artifact_url),
    artifactType: result.media_type,
    logId: result.log_id,
    angle: result.angle,
    transitions: result.transitions ?? [],
    angleSummary,
    // Keep the raw AnalysisPayload so result-driven views (crop/zoom overlays,
    // angle-vs-state charts) can read bbox/per-light angles without re-deriving
    // them from the display-shaped scenario fields above.
    rawResult: result,
  }
}
