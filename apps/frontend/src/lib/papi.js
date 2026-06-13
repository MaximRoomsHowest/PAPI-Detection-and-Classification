import { backendStateId, stateCatalog } from '../catalog/stateCatalog'
import { percent } from './format'
import { mediaUrl } from './api'
import { transitionEventsForResult } from './insightsTransforms'

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
    inferred: Boolean(lamp.inferred),
    inferenceNote: lamp.inference_note ?? null,
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
        // The raw backend enum (request_metadata/file_metadata/telemetry_file/
        // metadata) — `source` above gets localized for display, so logic that
        // needs to know WHETHER telemetry existed keys on this instead (FE-17).
        sourceId: result.angle.angle_source ?? null,
        note: result.angle.angle_note,
        // Runway<->metadata sanity: false when the drone fix is implausibly far from
        // the selected runway (wrong runway / datum). All ??-guarded so an older
        // payload without these fields stays available + plausible (back-compat).
        plausible: result.angle.plausible ?? true,
        plausibilityNote: result.angle.plausibility_note ?? null,
        nearestLampDistanceM: result.angle.nearest_lamp_distance_m ?? null,
        // First-order 1-sigma band (deg) from DJI RTK std; null unless the file had it.
        uncertainty: result.angle.elevation_angle_uncertainty_deg ?? null,
      }
    : {
        available: false,
        value: 'N/A',
        source: 'missing metadata',
        // Still set when telemetry WAS resolved but the angle solve failed
        // (angle_available=true, elevation null) — the provenance strip uses
        // it to avoid claiming "telemetry: none" in that case (FE-17).
        sourceId: result.angle?.angle_source ?? null,
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
    artifactUrl: context.artifactUrl ?? mediaUrl(result.artifact_url),
    artifactType: result.media_type,
    logId: result.log_id,
    angle: result.angle,
    transitions: transitionEventsForResult(result),
    // Raw per-frame confidence + verdict series for video / folder analyses
    // (empty for single images). Drives the Live Demo frame-by-frame chart.
    perFrame: result.per_frame ?? [],
    angleSummary,
    // Keep the raw AnalysisPayload so result-driven views (crop/zoom overlays,
    // angle-vs-state charts) can read bbox/per-light angles without re-deriving
    // them from the display-shaped scenario fields above.
    rawResult: result,
  }
}

function lampFromFrameState(lamp) {
  return {
    index: lamp.index,
    state: lamp.state,
    confidence: lamp.confidence,
    bbox: lamp.bbox ?? null,
    inferred: Boolean(lamp.inferred),
    inference_note: lamp.inference_note ?? null,
  }
}

function completeFrameLamps(lamps) {
  const byIndex = new Map((lamps ?? []).map((lamp) => [lamp.index, lamp]))

  return [1, 2, 3, 4].map((index) =>
    byIndex.has(index)
      ? lampFromFrameState(byIndex.get(index))
      : { index, state: 'unknown', confidence: 0, bbox: null },
  )
}

function sampleClosestToFrame(samples, frameIndex) {
  if (!samples?.length) {
    return null
  }

  return samples.reduce((closest, sample) => {
    const currentDistance = Math.abs((sample.frame_index ?? 0) - frameIndex)
    const closestDistance = Math.abs((closest.frame_index ?? 0) - frameIndex)
    return currentDistance < closestDistance ? sample : closest
  })
}

// ``labels`` carries the caller's localized templates (useAnalysis passes the
// active locale's copy.live strings); the English defaults only backstop
// direct library use outside the app.
export function scenarioFromVideoFrameResult(result, baseScenario, frameIndex, labels = {}) {
  const {
    angleUnavailable = 'Angle unavailable',
    framesLabel = '{count} labeled frames',
  } = labels
  const perFrame = result.per_frame ?? []
  const framePoint = sampleClosestToFrame(perFrame, frameIndex)
  const angleSample = sampleClosestToFrame(result.angle_track ?? [], frameIndex)
  const globalState = framePoint?.state ?? result.global_state
  const stateId = backendStateId[globalState] ?? 'unknown'
  const activeState = stateCatalog.find((state) => state.id === stateId) ?? stateCatalog[stateCatalog.length - 1]
  const frameLamps = framePoint?.lamps?.length
    ? completeFrameLamps(framePoint.lamps)
    : angleSample?.lamps?.length
      ? completeFrameLamps(angleSample.lamps)
      : result.lamps
  const frameResult = {
    ...result,
    global_state: globalState,
    lamps: frameLamps,
    confidence: framePoint?.confidence ?? result.confidence,
    angle: angleSample
      ? {
          ...result.angle,
          angle_available: true,
          elevation_angle_deg: angleSample.elevation_angle_deg,
        }
      : result.angle,
  }
  // The result panel shows the aggregate count label (the per-frame position
  // already lives in the frame navigator), so the label carries the count and
  // totalFrames stays 1 to suppress the "of N" suffix.
  const totalFrames = result.frame_count ?? perFrame.length ?? 1
  const scenario = scenarioFromBackendResult(
    frameResult,
    {
      frameLabel: framesLabel.replace('{count}', String(totalFrames)),
      totalFrames: 1,
      artifactUrl: baseScenario?.artifactUrl,
    },
    angleUnavailable,
  )

  return {
    ...scenario,
    summary: `${lampPattern(frameLamps)} = ${activeState.label.toLowerCase()}`,
    transitions: baseScenario?.transitions ?? scenario.transitions,
    perFrame,
    artifactUrl: baseScenario?.artifactUrl ?? scenario.artifactUrl,
    artifactType: baseScenario?.artifactType ?? scenario.artifactType,
    rawResult: result,
  }
}
