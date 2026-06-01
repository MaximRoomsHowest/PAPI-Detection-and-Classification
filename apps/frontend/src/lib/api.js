const API_BASE_URL = (import.meta.env.VITE_PAPI_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const API_KEY = import.meta.env.VITE_PAPI_API_KEY

// Upload + timeout guards (audit F-MAJ-8). Defaults are intentionally close
// to the backend's own limits so users see a fast client-side error rather
// than waiting for a 413 / hung request.
const DEFAULT_MAX_UPLOAD_MB = 100
const DEFAULT_REQUEST_TIMEOUT_MS = 60_000

const MAX_UPLOAD_BYTES =
  Number(import.meta.env.VITE_PAPI_MAX_UPLOAD_MB ?? DEFAULT_MAX_UPLOAD_MB) * 1024 * 1024
const REQUEST_TIMEOUT_MS = Number(
  import.meta.env.VITE_PAPI_REQUEST_TIMEOUT_MS ?? DEFAULT_REQUEST_TIMEOUT_MS,
)
// Inference is sequential at ~0.4 fps, so a long video (up to 600 frames) or a
// folder batch (up to 200 images) can legitimately run for many minutes — far
// past the 60s GET timeout. The three analyze calls get their own generous budget
// so the headline video/batch features aren't aborted mid-analysis (audit H2).
const DEFAULT_ANALYZE_TIMEOUT_MS = 30 * 60_000
const ANALYZE_TIMEOUT_MS = Number(
  import.meta.env.VITE_PAPI_ANALYZE_TIMEOUT_MS ?? DEFAULT_ANALYZE_TIMEOUT_MS,
)

function buildHeaders(extra = {}) {
  const headers = { ...extra }
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY
  }
  return headers
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  const value = bytes / Math.pow(1024, exponent)
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[exponent]}`
}

function checkUploadSize(files) {
  const fileList = Array.isArray(files) ? files : [files]
  let totalBytes = 0
  for (const file of fileList) {
    if (!file || typeof file.size !== 'number') continue
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error(
        `File "${file.name}" is ${formatBytes(file.size)}, which exceeds the ${formatBytes(MAX_UPLOAD_BYTES)} per-file limit. Compress or trim the file before uploading.`,
      )
    }
    totalBytes += file.size
  }
  // Folder uploads can be many files at once; cap aggregate size too.
  const aggregateLimit = MAX_UPLOAD_BYTES * 4
  if (fileList.length > 1 && totalBytes > aggregateLimit) {
    throw new Error(
      `Folder upload totals ${formatBytes(totalBytes)} across ${fileList.length} files, exceeding the ${formatBytes(aggregateLimit)} batch limit.`,
    )
  }
}

/**
 * Wrap a fetch call with an AbortController so a hung backend can't leave the
 * UI spinning forever. The signal is the only way to give fetch() a timeout
 * in the browser — there is no built-in timeout option.
 */
async function fetchWithTimeout(input, init = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    // no-store: API responses (logs, stats, model) must never be served from
    // the browser HTTP cache, or the History "Refresh" button could re-render
    // stale rows after a new analysis was logged.
    return await fetch(input, { ...init, cache: 'no-store', signal: controller.signal })
  } catch (error) {
    if (error?.name === 'AbortError') {
      // Attach the original AbortError as the cause so devtools / Sentry
      // / future error boundaries can inspect both layers (preserve-caught-error).
      throw new Error(
        `Backend did not respond within ${Math.round(timeoutMs / 1000)} s. The request may still finish server-side — refresh logs to verify.`,
        { cause: error },
      )
    }
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

export function mediaUrl(path) {
  if (!path) {
    return null
  }
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

export async function fetchRunways() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/runways`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load runways (${response.status})`)
  }
  return response.json()
}

export async function fetchModelInfo() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/model`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load model info (${response.status})`)
  }
  return response.json()
}

export async function fetchStats() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/stats`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load inference stats (${response.status})`)
  }
  return response.json()
}

/**
 * Build the shared querystring for /api/logs and /api/logs/export.csv from a
 * camelCase options object (audit IMP-BE-3 filters). Empty/absent values are
 * omitted so `fetchLogs()` with no args still hits a bare `/api/logs`.
 */
function buildLogQuery({
  limit,
  offset,
  runwayId,
  mediaType,
  globalState,
  createdAfter,
  minConfidence,
} = {}) {
  const params = new URLSearchParams()
  if (limit != null) params.set('limit', String(limit))
  if (offset != null) params.set('offset', String(offset))
  if (runwayId) params.set('runway_id', runwayId)
  if (mediaType) params.set('media_type', mediaType)
  if (globalState) params.set('global_state', globalState)
  if (createdAfter) params.set('created_after', createdAfter)
  if (minConfidence != null && minConfidence !== '') params.set('min_confidence', String(minConfidence))
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export async function fetchLogs(options = {}) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/logs${buildLogQuery(options)}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load analysis history (${response.status})`)
  }
  const data = await response.json()
  const items = Array.isArray(data) ? data : []
  // X-Total-Count lets the History page show "page N of M" (audit IMP-BE-3).
  // Guard for stubbed responses (tests) that have no headers object.
  const totalHeader = response.headers?.get?.('X-Total-Count')
  const total = totalHeader != null && totalHeader !== '' ? Number(totalHeader) : items.length
  return { items, total }
}

export function logsCsvUrl(options = {}) {
  return `${API_BASE_URL}/api/logs/export.csv${buildLogQuery(options)}`
}

/**
 * Download the (optionally filtered) analysis log as a CSV file. Uses fetch +
 * a blob URL rather than a plain <a href> so the X-API-Key header is sent —
 * a bare link would 401 when an API key is configured (audit IMP-BE-4 / IMP-BE-6).
 */
export async function downloadLogsCsv(options = {}, filename = 'papi_analysis_logs.csv') {
  const response = await fetchWithTimeout(logsCsvUrl(options), { headers: buildHeaders() })
  if (!response.ok) {
    throw new Error(`Could not export logs (${response.status})`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function fetchLogDetail(logId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/logs/${logId}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load analysis ${logId} (${response.status})`)
  }
  return response.json()
}

export async function fetchSystem() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/system`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load system info (${response.status})`)
  }
  return response.json()
}

/**
 * Poll the backend readiness probe for a topbar status indicator (audit IMP-FE-17).
 * Resilient by design — returns ``{ ok: false }`` instead of throwing so a down
 * backend just shows "offline" rather than crashing the page.
 */
export async function fetchReady() {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/health/ready`, {
      headers: buildHeaders(),
    })
    const body = await response.json().catch(() => ({}))
    return { ok: response.ok, ...body }
  } catch {
    return { ok: false, status: 'unreachable' }
  }
}

async function parseAnalysisResponse(response) {
  if (!response.ok) {
    let detail = `Analysis failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }

  return response.json()
}

/**
 * Append optional drone-telemetry metadata to an analyze request. The backend
 * reads snake_case form fields and treats every one as optional (runway_id
 * falls back to its own 'papi_24' default); empty strings are omitted so an
 * untouched field never overrides a backend default or a real EXIF GPS read.
 * The api.test.js "optional metadata" case pins this contract.
 */
function appendMetadata(formData, metadata = {}) {
  const fields = {
    runway_id: metadata.runwayId,
    drone_id: metadata.droneId,
    drone_latitude: metadata.droneLatitude,
    drone_longitude: metadata.droneLongitude,
    drone_altitude_m: metadata.droneAltitudeM,
  }
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== '') {
      formData.append(key, value)
    }
  }
}

export async function analyzeFrame(file, metadata) {
  checkUploadSize(file)
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze-frame`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
  )

  return parseAnalysisResponse(response)
}

export async function analyzeFrames(files, metadata) {
  checkUploadSize(files)
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  appendMetadata(formData, metadata)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze-frames`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
  )

  return parseAnalysisResponse(response)
}

export async function analyzeMedia(file, metadata) {
  checkUploadSize(file)
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
  )

  return parseAnalysisResponse(response)
}
