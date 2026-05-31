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
