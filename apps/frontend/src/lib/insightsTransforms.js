// Pure data transforms for the Insights charts. Kept out of the component files
// so the components export only components (react-refresh) and so the transforms
// can be unit-tested in isolation. Every function reads only real backend
// fields — there is no fabrication anywhere in here.

// "obscured" sits on its own tier below red so a lamp the detector never found is
// still plotted against the viewing angle (client ask: surface non-detections in
// the graphs). A bare "unknown" has no tier and is intentionally dropped.
const STATE_NUM = { obscured: -1, red: 0, transition: 1, white: 2 }

// FAA-standard set angles for a 3.0 deg glideslope — DISPLAY REFERENCE ONLY.
// EDNY's commissioned per-lamp values are still unconfirmed (the comparison the
// summary strip calls "pending"), so charts compare these SORTED-to-SORTED,
// never slot-by-slot. Mirrors faa_default_set_angles_deg in the backend's
// state.py / configs/papi_edny.yaml.
export const FAA_DEFAULT_SET_ANGLES_DEG = [2.5, 2.83, 3.17, 3.5]

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

const TRANSITION_MAX_FRAME_GAP = 2

function denoiseFrameStates(points) {
  if (points.length < 3) {
    return points
  }
  return points.map((point, i) => {
    if (i === 0 || i === points.length - 1) {
      return point
    }
    const prev = points[i - 1]
    const next = points[i + 1]
    const isOneFrameBlip =
      point.state !== prev.state &&
      prev.state === next.state &&
      point.frame_index - prev.frame_index > 0 &&
      point.frame_index - prev.frame_index <= TRANSITION_MAX_FRAME_GAP &&
      next.frame_index - point.frame_index > 0 &&
      next.frame_index - point.frame_index <= TRANSITION_MAX_FRAME_GAP
    return isOneFrameBlip ? { ...point, state: prev.state } : point
  })
}

function isColourTransition(event) {
  return (
    event &&
    (event.from_state === 'red' || event.from_state === 'white') &&
    (event.to_state === 'red' || event.to_state === 'white') &&
    event.from_state !== event.to_state &&
    Number.isInteger(event.lamp_index) &&
    Number.isFinite(event.frame_index)
  )
}

function suppressReversalBlips(events) {
  const grouped = new Map()
  for (const event of events) {
    if (!grouped.has(event.lamp_index)) {
      grouped.set(event.lamp_index, [])
    }
    grouped.get(event.lamp_index).push(event)
  }

  const stable = []
  for (const group of grouped.values()) {
    const kept = []
    for (const event of group.toSorted((a, b) => a.frame_index - b.frame_index)) {
      const previous = kept[kept.length - 1]
      const isImmediateReversal =
        previous &&
        event.frame_index - previous.frame_index > 0 &&
        event.frame_index - previous.frame_index <= TRANSITION_MAX_FRAME_GAP &&
        previous.from_state === event.to_state &&
        previous.to_state === event.from_state
      if (isImmediateReversal) {
        kept.pop()
      } else {
        kept.push(event)
      }
    }
    stable.push(...kept)
  }
  return stable.toSorted((a, b) => a.frame_index - b.frame_index || a.lamp_index - b.lamp_index)
}

function stableBackendTrackingEvents(result) {
  if (!Array.isArray(result?.transitions) || result.transition_method === 'model') {
    return null
  }
  const events = result.transitions
    .filter(isColourTransition)
    .map((event) => ({ ...event, method: event.method ?? 'tracking' }))
  return suppressReversalBlips(events)
}

function stableTrackingEventsFromAngleTrack(result) {
  const track = result?.angle_track
  if (!Array.isArray(track) || track.length === 0 || result?.transition_method === 'model') {
    return null
  }

  const events = []
  for (let lampIndex = 1; lampIndex <= 4; lampIndex += 1) {
    const points = denoiseFrameStates(
      track
        .map((sample) => {
          const lamp = (sample?.lamps ?? []).find((entry) => entry.index === lampIndex)
          if (!lamp || (lamp.state !== 'red' && lamp.state !== 'white')) {
            return null
          }
          return {
            frame_index: sample.frame_index,
            elevation_angle_deg: sample.elevation_angle_deg,
            state: lamp.state,
          }
        })
        .filter((point) => point && Number.isFinite(point.frame_index))
        .sort((a, b) => a.frame_index - b.frame_index),
    )

    const first = points[0]
    const last = points[points.length - 1]
    if (!first || !last || first.state === last.state) {
      continue
    }

    const lastOppositeIndex = points.findLastIndex((point) => point.state !== last.state)
    const current = points[lastOppositeIndex + 1]
    const previous = points[lastOppositeIndex]
    if (!previous || !current) {
      continue
    }
    const gap = current.frame_index - previous.frame_index
    if (gap > 0 && gap <= TRANSITION_MAX_FRAME_GAP && previous.state !== current.state) {
      events.push({
        lamp_index: lampIndex,
        from_state: previous.state,
        to_state: current.state,
        frame_index: current.frame_index,
        elevation_angle_deg: Number.isFinite(current.elevation_angle_deg) ? current.elevation_angle_deg : null,
        method: 'tracking',
      })
    }
  }
  events.sort((a, b) => a.frame_index - b.frame_index || a.lamp_index - b.lamp_index)
  return events
}

export function transitionEventsForResult(result) {
  if (result?.transition_method === 'model') {
    return (result?.transitions ?? []).filter(isColourTransition)
  }
  const backendEvents = stableBackendTrackingEvents(result)
  if (backendEvents !== null) {
    return backendEvents
  }
  return stableTrackingEventsFromAngleTrack(result) ?? []
}

export function stableTransitionEvents(results) {
  return (results ?? []).flatMap((result) => transitionEventsForResult(result))
}

function hasBackendTransitionAuthority(result) {
  return result?.transition_method === 'model' || Array.isArray(result?.transitions)
}

// The headline PAPI-verification numbers, one entry per light:
//   settledAngle — the lamp's stabilized red<->white crossing angle when a
//                  transition event provides one; otherwise the angle-vs-state
//                  midpoint fallback. This keeps the chart marker aligned with
//                  the visible event table for tracked videos.
//   bandMin/bandMax — the stabilized event zone: lowest/highest angle at which
//                  the tracker logged a sustained flip for this lamp;
//   flips        — how many stabilized red<->white switches the tracker logged
//                  after one-frame blip suppression.
export function transitionAngleSummary(results) {
  const list = results ?? []
  const states = angleVsStateSeries(results)
  const fallbackStates = angleVsStateSeries(list.filter((result) => !hasBackendTransitionAuthority(result)))
  const bands = [1, 2, 3, 4].map(() => ({ flips: 0, bandMin: null, bandMax: null, eventAngles: [] }))
  for (const result of list) {
    for (const event of transitionEventsForResult(result)) {
      const index = event.lamp_index
      if (!(index >= 1 && index <= 4)) {
        continue
      }
      const entry = bands[index - 1]
      entry.flips += 1
      const angle = event.elevation_angle_deg
      if (Number.isFinite(angle)) {
        entry.eventAngles.push(angle)
        entry.bandMin = entry.bandMin === null ? angle : Math.min(entry.bandMin, angle)
        entry.bandMax = entry.bandMax === null ? angle : Math.max(entry.bandMax, angle)
      }
    }
  }
  return states.map((lamp, i) => {
    const eventAngles = bands[i].eventAngles
    const eventAngle = eventAngles.length === 1 ? eventAngles[0] : null
    const fallbackAngle = fallbackStates[i]?.transitionAngle
    return {
      lampIndex: lamp.lampIndex,
      settledAngle: Number.isFinite(eventAngle)
        ? eventAngle
        : Number.isFinite(fallbackAngle) ? fallbackAngle : null,
      bandMin: bands[i].bandMin,
      bandMax: bands[i].bandMax,
      flips: bands[i].flips,
    }
  })
}

export function transitionFlickerStatus(flipCount) {
  if (!Number.isFinite(flipCount) || flipCount <= 0) return 'no_crossing'
  if (flipCount === 1) return 'clean_crossing'
  return 'review_flicker'
}

function csvCell(value) {
  if (value === null || value === undefined) return ''
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function transitionCsv(results, source = {}) {
  const headers = [
    'source',
    'log_id',
    'runway_id',
    'original_filename',
    'transition_method',
    'lamp_index',
    'from_state',
    'to_state',
    'frame_index',
    'elevation_angle_deg',
    'method',
    'flicker_status',
  ]
  const rows = []
  for (const result of results ?? []) {
    const counts = new Map()
    for (const event of transitionEventsForResult(result)) {
      if (Number.isInteger(event?.lamp_index) && event.lamp_index >= 1 && event.lamp_index <= 4) {
        counts.set(event.lamp_index, (counts.get(event.lamp_index) ?? 0) + 1)
      }
    }
    for (const event of transitionEventsForResult(result)) {
      if (!Number.isInteger(event?.lamp_index) || event.lamp_index < 1 || event.lamp_index > 4) {
        continue
      }
      rows.push([
        source.mode ?? '',
        result?.log_id ?? source.logId ?? '',
        result?.runway_id ?? '',
        result?.original_filename ?? '',
        result?.transition_method ?? '',
        event.lamp_index,
        event.from_state ?? '',
        event.to_state ?? '',
        event.frame_index ?? '',
        Number.isFinite(event.elevation_angle_deg) ? event.elevation_angle_deg : '',
        event.method ?? '',
        transitionFlickerStatus(counts.get(event.lamp_index) ?? 0),
      ])
    }
  }
  return [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')
}

// --- Per-frame lamp-state bands ------------------------------------------------

// z-code order for the state-band heatmap. Index IS the code: a lamp slot absent
// from a frame's detections is 'unknown' (0) — honest "not seen this frame".
export const STATE_BAND_CODES = ['unknown', 'obscured', 'red', 'transition', 'white']
const STATE_BAND_CODE = Object.fromEntries(STATE_BAND_CODES.map((state, code) => [state, code]))

// One band block per analysed video/sequence that carried a per-frame track:
// frames/angles on x, Lights 1..4 as rows, z[lampRow][frameCol] = state code.
// This is the "what was every lamp showing at every moment" view the flip-marker
// timeline could not give — flicker shows up as thin alternating stripes exactly
// where the lamp passes through its blend zone.
export function stateBandSeries(results) {
  const blocks = []
  for (const result of results ?? []) {
    const perFrame = Array.isArray(result?.per_frame) ? result.per_frame.filter((sample) => Array.isArray(sample?.lamps)) : []
    const track = result?.angle_track
    const source = perFrame.length > 0 ? perFrame : track
    if (!Array.isArray(source) || source.length === 0) {
      continue
    }
    const angleByFrame = new Map(
      (Array.isArray(track) ? track : [])
        .filter((sample) => Number.isFinite(sample?.frame_index))
        .map((sample) => [sample.frame_index, sample.elevation_angle_deg]),
    )
    const frames = []
    const angles = []
    const z = [[], [], [], []]
    for (const sample of source) {
      if (!Number.isFinite(sample?.frame_index)) {
        continue
      }
      frames.push(sample.frame_index)
      const angle = sample.elevation_angle_deg ?? angleByFrame.get(sample.frame_index)
      angles.push(Number.isFinite(angle) ? angle : null)
      for (let lampIndex = 1; lampIndex <= 4; lampIndex += 1) {
        const lamp = (sample.lamps ?? []).find((entry) => entry.index === lampIndex)
        z[lampIndex - 1].push(STATE_BAND_CODE[lamp?.state] ?? STATE_BAND_CODE.unknown)
      }
    }
    if (frames.length > 0) {
      const label =
        result?.original_filename ??
        (result?.log_id ? `log ${result.log_id.slice(0, 8)}` : `series ${blocks.length + 1}`)
      blocks.push({ label, frames, angles, z })
    }
  }
  return blocks
}

// --- Session distributions ---------------------------------------------------

// One zeroed tally per countable lamp state. The exact key set also acts as the
// allow-list below: a lamp whose state isn't one of these keys is ignored.
const emptyStateBucket = () => ({ white: 0, red: 0, transition: 0, obscured: 0, unknown: 0 })

// Per-light state counts across the session. A result that carries a per-frame
  // per_frame is counted PER FRAME when present (the honest mix for a sweep — the old
// aggregate-only counting showed "100% red" for a video whose lamps spent 40%
// of frames white, because the aggregate verdict is one majority state per
  // lamp). A lamp slot absent from a frame's detections counts as 'unknown'.
  // Older results without per_frame can still fall back to angle_track; results
  // without either frame series keep the aggregate lamps[] counting.
export function perLightStateSeries(results) {
  const counts = [1, 2, 3, 4].map(emptyStateBucket)
  for (const result of results ?? []) {
    const perFrame = Array.isArray(result?.per_frame) ? result.per_frame.filter((sample) => Array.isArray(sample?.lamps)) : []
    if (perFrame.length > 0) {
      for (const sample of perFrame) {
        for (let lampIndex = 1; lampIndex <= 4; lampIndex += 1) {
          const lamp = (sample?.lamps ?? []).find((entry) => entry.index === lampIndex)
          const bucket = counts[lampIndex - 1]
          if (lamp === undefined) {
            bucket.unknown += 1
          } else if (bucket[lamp.state] !== undefined) {
            bucket[lamp.state] += 1
          }
        }
      }
      continue
    }
    const track = result?.angle_track
    if (Array.isArray(track) && track.length > 0) {
      for (const sample of track) {
        for (let lampIndex = 1; lampIndex <= 4; lampIndex += 1) {
          const lamp = (sample?.lamps ?? []).find((entry) => entry.index === lampIndex)
          const bucket = counts[lampIndex - 1]
          if (lamp === undefined) {
            bucket.unknown += 1
          } else if (bucket[lamp.state] !== undefined) {
            bucket[lamp.state] += 1
          }
        }
      }
      continue
    }
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
  const fallbackStates = angleVsStateSeries(list.filter((result) => !hasBackendTransitionAuthority(result)))
  const lampsDetected = states.filter((lamp) => lamp.points.length > 0).length
  const crossedLampIndices = new Set(
    stableTransitionEvents(list)
      .filter((event) => Number.isInteger(event?.lamp_index) && event.lamp_index >= 1 && event.lamp_index <= 4)
      .map((event) => event.lamp_index),
  )
  for (const lamp of fallbackStates) {
    if (Number.isFinite(lamp.transitionAngle)) {
      crossedLampIndices.add(lamp.lampIndex)
    }
  }
  const lampsCrossed = crossedLampIndices.size

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
