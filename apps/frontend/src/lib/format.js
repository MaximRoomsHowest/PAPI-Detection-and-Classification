// Internal helper for percent(); not exported because nothing else imports it
// (cropRect.js has its own local clamp).
function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export function percent(value) {
  return Math.round(clamp(Number(value) || 0, 0, 1) * 100)
}

export function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString([], {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatAngle(value, fallback = '—') {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(3)}°` : fallback
}

// 2-dp angle for insights tables/summaries: three decimals asserted a precision the
// ~0.1° elevation uncertainty doesn't support and were harder to scan (readability audit).
export function degrees(value, fallback = '—') {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)}°` : fallback
}

// Human-readable duration: sub-second renders as ms, 1s+ as seconds, so a video
// figure (e.g. 45000 ms) reads as "45 s" instead of a wall of milliseconds.
// Returns { value, suffix } to match the InlineMetric props.
export function formatDurationMs(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n) || n < 0) {
    return { value: 0, suffix: ' ms' }
  }
  if (n >= 1000) {
    return { value: (n / 1000).toFixed(n >= 10000 ? 0 : 1), suffix: ' s' }
  }
  return { value: Math.round(n), suffix: ' ms' }
}

// Human-readable horizontal distance: metres under 1 km, else kilometres.
export function formatDistanceM(meters) {
  if (meters == null) return ''
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`
}
