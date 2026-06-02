// Pure data transforms for the Insights charts. Kept out of the component files
// so the components export only components (react-refresh) and so the transforms
// can be unit-tested in isolation. Every function reads only real backend
// fields — there is no fabrication anywhere in here.

// "obscured" sits on its own tier below red so a lamp the detector never found is
// still plotted against the viewing angle (client ask: surface non-detections in
// the graphs). A bare "unknown" has no tier and is intentionally dropped.
const STATE_NUM = { obscured: -1, red: 0, transition: 1, white: 2 }

// --- Angle vs. light state ---------------------------------------------------

// Per-light angle resolution: prefer the lamp's own elevation angle, fall back
// to the frame-level (averaged) angle. Returns null when no real angle exists.
export function resolveAngle(angle, lampIndex) {
  if (!angle?.angle_available) {
    return null
  }
  const perLightEntry = angle.per_light_angles?.find((entry) => entry.runway_lamp === lampIndex)
  // ?? (not ||) so a legitimate 0 deg per-light angle is kept; only a
  // null/undefined per-light value falls through to the frame-level angle.
  const value = perLightEntry?.elevation_angle_deg ?? angle.elevation_angle_deg
  return Number.isFinite(value) ? value : null
}

// Build per-light (angle, state) point series from raw AnalysisPayload[]. Only
// results with `angle.angle_available` contribute. "obscured" lamps DO appear (on
// their own tier below red) so non-detections show up against angle; a bare
// `unknown` state has no tier on the axis and is skipped.
export function angleVsStateSeries(results) {
  const series = [1, 2, 3, 4].map((lampIndex) => ({ lampIndex, points: [] }))
  for (const result of results ?? []) {
    const angleData = result?.angle
    if (!angleData?.angle_available) {
      continue
    }
    for (const lamp of result.lamps ?? []) {
      const lampIndex = lamp.index
      if (!(lampIndex >= 1 && lampIndex <= 4)) {
        continue
      }
      const stateNum = STATE_NUM[lamp.state]
      if (stateNum === undefined) {
        continue
      }
      const angle = resolveAngle(angleData, lampIndex)
      if (angle === null) {
        continue
      }
      series[lampIndex - 1].points.push({
        angle,
        stateNum,
        state: lamp.state,
        confidence: Math.round((lamp.confidence ?? 0) * 100),
        label: result.original_filename ?? (result.log_id ? `log ${result.log_id.slice(0, 8)}` : ''),
      })
    }
  }
  // Sort by angle so the optional step line reads left-to-right.
  for (const lamp of series) {
    lamp.points.sort((a, b) => a.angle - b.angle)
  }
  return series
}

// --- Transitions -------------------------------------------------------------

// Count red↔white switches per light from backend transitions[].
export function transitionCountSeries(transitions) {
  const counts = [0, 0, 0, 0]
  for (const event of transitions ?? []) {
    const index = event.lamp_index
    if (index >= 1 && index <= 4) {
      counts[index - 1] += 1
    }
  }
  return { lamps: [1, 2, 3, 4], counts }
}

// --- Session distributions ---------------------------------------------------

// One zeroed tally per countable lamp state. The exact key set also acts as the
// allow-list below: a lamp whose state isn't one of these keys is ignored.
const emptyStateBucket = () => ({ white: 0, red: 0, transition: 0, obscured: 0, unknown: 0 })

// Per-light state counts across the session's results (real lamps[].state).
export function perLightStateSeries(results) {
  const counts = [1, 2, 3, 4].map(emptyStateBucket)
  for (const result of results ?? []) {
    for (const lamp of result?.lamps ?? []) {
      const bucket = lamp.index >= 1 && lamp.index <= 4 ? counts[lamp.index - 1] : null
      // The `!== undefined` check keeps an unexpected state from creating a
      // stray key (which would skew totals and change the bucket shape).
      if (bucket && bucket[lamp.state] !== undefined) {
        bucket[lamp.state] += 1
      }
    }
  }
  return counts
}

// Detection confidence (%) for every actually-detected lamp across the session.
// Undetected slots (state 'unknown', confidence 0) are excluded so the
// distribution reflects real detections, not empty lamp positions.
export function confidenceValues(results) {
  const values = []
  for (const result of results ?? []) {
    for (const lamp of result?.lamps ?? []) {
      if (Number.isFinite(lamp.confidence) && lamp.confidence > 0) {
        values.push(Math.round(lamp.confidence * 100))
      }
    }
  }
  return values
}
