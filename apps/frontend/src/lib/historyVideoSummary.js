import { lampStateLabel } from './stateLabels'

export const VIDEO_STATE_COLUMNS = ['red', 'white', 'transition', 'obscured', 'unknown']

export function videoFrameSamples(log) {
  return Array.isArray(log?.per_frame) ? log.per_frame : []
}

export function averageFrameConfidence(samples) {
  const values = samples
    .map((sample) => Number(sample?.confidence))
    .filter((value) => Number.isFinite(value))
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

export function dominantFrameState(samples) {
  const counts = new Map()
  for (const sample of samples) {
    if (!sample?.state) continue
    counts.set(sample.state, (counts.get(sample.state) ?? 0) + 1)
  }
  let bestState = null
  let bestCount = -1
  for (const [state, count] of counts.entries()) {
    if (count > bestCount) {
      bestState = state
      bestCount = count
    }
  }
  return bestState
}

export function videoResultSummary(log) {
  const samples = videoFrameSamples(log)
  if (log?.media_type !== 'video' || samples.length === 0) {
    return null
  }
  return {
    frameCount: samples.length,
    confidence: averageFrameConfidence(samples),
    globalState: dominantFrameState(samples),
  }
}

export function frameLampPattern(sample, copy) {
  const byIndex = new Map((sample?.lamps ?? []).map((lamp) => [lamp.index, lamp.state]))
  return [1, 2, 3, 4]
    .map((index) => `L${index} ${lampStateLabel(byIndex.get(index) ?? 'unknown', copy)}`)
    .join(' · ')
}
