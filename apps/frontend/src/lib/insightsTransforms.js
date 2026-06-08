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

// Collapse a single-sample state that differs from BOTH equal neighbours (a one-frame
// mis-classification blip) into the neighbours' state, so a lone spurious "white" frame
// at a low angle doesn't get read as the transition. Real transitions persist across
// several frames, so this only removes noise. Endpoints are left untouched.
function denoiseStates(colored) {
  if (colored.length < 3) {
    return colored
  }
  return colored.map((point, i) => {
    if (i === 0 || i === colored.length - 1) {
      return point
    }
    const prev = colored[i - 1]
    const next = colored[i + 1]
    return point.state !== prev.state && prev.state === next.state ? { ...point, state: prev.state } : point
  })
}

// Estimate the angle at which a lamp switches red <-> white (its PAPI transition
// angle): the midpoint of the first red/transition <-> white boundary in the
// angle-sorted, blip-denoised samples, in EITHER direction. An ascending capture
// crosses red->white (a lamp below its set angle climbs above it); a descending
// capture crosses white->red. Returns null when the lamp never crosses (all-red,
// all-white, or no coloured samples). Pure detection from the real classified states —
// nothing modelled, and no fabricated angle for a lamp that never transitions.
export function detectTransitionAngle(points) {
  const colored = denoiseStates(
    (points ?? [])
      .filter((point) => point.state === 'red' || point.state === 'white' || point.state === 'transition')
      .sort((a, b) => a.angle - b.angle),
  )
  for (let i = 1; i < colored.length; i += 1) {
    const previous = colored[i - 1]
    const current = colored[i]
    // XOR on "is white": exactly one side of the pair is white -> a red/transition
    // <-> white boundary, regardless of climb/descent direction.
    if ((current.state === 'white') !== (previous.state === 'white')) {
      return (previous.angle + current.angle) / 2
    }
  }
  return null
}

// Build per-light (angle, state) point series from raw AnalysisPayload[]. Only
// results with `angle.angle_available` contribute. "obscured" lamps DO appear (on
// their own tier below red) so non-detections show up against angle; a bare
// `unknown` state has no tier on the axis and is skipped.
export function angleVsStateSeries(results) {
  const series = [1, 2, 3, 4].map((lampIndex) => ({ lampIndex, points: [] }))
  for (const result of results ?? []) {
    const label = result?.original_filename ?? (result?.log_id ? `log ${result.log_id.slice(0, 8)}` : '')
    const track = result?.angle_track

    // Per-frame sweep (video / sequence analysed with a telemetry track): each frame
    // contributes one (angle, state) point per lamp it was seen in, so the chart shows
    // the genuine red->white crossing across the descent — the client's AGL tool view.
    if (Array.isArray(track) && track.length > 0) {
      for (const sample of track) {
        const angle = sample?.elevation_angle_deg
        if (!Number.isFinite(angle)) {
          continue
        }
        for (const lamp of sample.lamps ?? []) {
          const lampIndex = lamp.index
          if (!(lampIndex >= 1 && lampIndex <= 4)) {
            continue
          }
          const stateNum = STATE_NUM[lamp.state]
          if (stateNum === undefined) {
            continue
          }
          series[lampIndex - 1].points.push({
            angle,
            stateNum,
            state: lamp.state,
            confidence: Math.round((lamp.confidence ?? 0) * 100),
            // Real measured red-channel redness (0-255, high=red) — the client's
            // "Redness vs angle" Y; null when the backend couldn't measure it.
            redness: Number.isFinite(lamp.redness) ? lamp.redness : null,
            label,
          })
        }
      }
      continue
    }

    // Fallback: one aggregated (angle, lamps) point per result — a single image, or a
    // video/sequence whose telemetry was a single fix (no per-frame track to sweep).
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
        redness: Number.isFinite(lamp.redness) ? lamp.redness : null,
        label,
      })
    }
  }
  // Sort by angle so the line reads left-to-right, then detect each lamp's
  // red->white transition angle from its own sorted samples.
  for (const lamp of series) {
    lamp.points.sort((a, b) => a.angle - b.angle)
    lamp.transitionAngle = detectTransitionAngle(lamp.points)
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

// --- Elevation angle over frame (descent profile) ----------------------------

// One (frame_index, elevation_angle_deg) line per analysed video/sequence that
// carried a per-frame telemetry track (DJI .SRT / CSV). The client's deliverable-#3
// "elevation angle over time" view — a real read of `angle_track`, nothing modelled.
// Results without a track (single images, or telemetry that was a single fix) are
// skipped, so the chart only shows series it can honestly draw.
export function elevationOverFrameSeries(results) {
  const series = []
  for (const result of results ?? []) {
    const track = result?.angle_track
    if (!Array.isArray(track) || track.length === 0) {
      continue
    }
    const frames = []
    const angles = []
    for (const sample of track) {
      const angle = sample?.elevation_angle_deg
      if (Number.isFinite(sample?.frame_index) && Number.isFinite(angle)) {
        frames.push(sample.frame_index)
        angles.push(angle)
      }
    }
    if (frames.length > 0) {
      const label =
        result?.original_filename ??
        (result?.log_id ? `log ${result.log_id.slice(0, 8)}` : `series ${series.length + 1}`)
      series.push({ label, frames, angles })
    }
  }
  return series
}

// --- Session summary (verdict strip) -----------------------------------------

// One at-a-glance roll-up of the current session for the header strip: how many of the
// 4 lamps were seen to cross red<->white, the elevation band swept, frame count, runway,
// and a data-trust read (geometry plausibility + angle source + 1-sigma uncertainty).
// Pure read of real fields; it deliberately does NOT compute a pass/fail verdict — that
// needs the commissioned set-angles, which aren't on the frontend yet.
export function summarizeSession(results) {
  const list = results ?? []
  const states = angleVsStateSeries(list)
  const lampsDetected = states.filter((lamp) => lamp.points.length > 0).length
  const lampsCrossed = states.filter((lamp) => Number.isFinite(lamp.transitionAngle)).length

  const angles = []
  let frameCount = 0
  let anglePlausible = true
  let angleSource = null
  let maxUncertaintyDeg = null
  for (const result of list) {
    frameCount += Number.isFinite(result?.frame_count) ? result.frame_count : 1
    const track = result?.angle_track
    if (Array.isArray(track) && track.length > 0) {
      for (const sample of track) {
        if (Number.isFinite(sample?.elevation_angle_deg)) {
          angles.push(sample.elevation_angle_deg)
        }
      }
    } else if (result?.angle?.angle_available && Number.isFinite(result.angle.elevation_angle_deg)) {
      angles.push(result.angle.elevation_angle_deg)
    }
    const angle = result?.angle
    if (angle) {
      if (angle.plausible === false) {
        anglePlausible = false
      }
      if (!angleSource && angle.angle_source) {
        angleSource = angle.angle_source
      }
      if (Number.isFinite(angle.elevation_angle_uncertainty_deg)) {
        maxUncertaintyDeg = Math.max(maxUncertaintyDeg ?? 0, angle.elevation_angle_uncertainty_deg)
      }
    }
  }

  return {
    analysisCount: list.length,
    frameCount,
    runwayId: list.find((result) => result?.runway_id)?.runway_id ?? null,
    lampsDetected,
    lampsCrossed,
    totalLamps: 4,
    hasAngles: angles.length > 0,
    elevationMin: angles.length ? Math.min(...angles) : null,
    elevationMax: angles.length ? Math.max(...angles) : null,
    anglePlausible,
    angleSource,
    maxUncertaintyDeg,
  }
}
