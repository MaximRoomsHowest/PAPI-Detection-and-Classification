import { backendStateId, legalStateCatalog, stateCatalog } from '../catalog/stateCatalog'
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
    return 'unknown'
  })
  return labels.join(' + ')
}

export function evidenceForState(stateId, confidence) {
  const selectedIndex = Math.max(
    0,
    legalStateCatalog.findIndex((state) => state.id === stateId),
  )
  return legalStateCatalog.map((_, index) => {
    if (stateId === 'unknown') {
      return index === 2 ? 20 : 10
    }
    return index === selectedIndex ? percent(confidence) : Math.max(1, 18 - Math.abs(index - selectedIndex) * 5)
  })
}

export function scenarioFromBackendResult(result, context) {
  const stateId = backendStateId[result.global_state] ?? 'unknown'
  const activeState = stateCatalog.find((state) => state.id === stateId) ?? stateCatalog[stateCatalog.length - 1]
  const lamps = result.lamps.map((lamp) => ({
    id: lamp.index,
    status: lamp.state === 'unknown' ? 'occluded' : lamp.state,
    confidence: percent(lamp.confidence),
    transition: lamp.state === 'transition' ? percent(lamp.confidence) : Math.max(3, 100 - percent(lamp.confidence)),
    bbox: lamp.bbox,
  }))
  const angle = result.angle?.angle_available
    ? `${result.angle.elevation_angle_deg.toFixed(3)} deg`
    : 'Angle unavailable'
  const angleSummary = result.angle?.angle_available
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
    evidence: evidenceForState(stateId, result.confidence),
    environmentClass: 'clear',
    artifactUrl: mediaUrl(result.artifact_url),
    artifactType: result.media_type,
    logId: result.log_id,
    angle: result.angle,
    transitions: result.transitions ?? [],
    angleSummary,
  }
}
