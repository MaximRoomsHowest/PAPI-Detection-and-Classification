import { REQUEST_TIMEOUT_ERROR_CODE } from './errorMessages'

const API_BASE_URL = (import.meta.env.VITE_PAPI_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const API_KEY = import.meta.env.VITE_PAPI_API_KEY

// Upload + timeout guards (audit F-MAJ-8). Defaults are intentionally close
// to the backend's own limits so users see a fast client-side error rather
// than waiting for a 413 / hung request.
const DEFAULT_MAX_UPLOAD_MB = 100
const DEFAULT_REQUEST_TIMEOUT_MS = 60_000

// Parse a numeric env override, falling back to the default when the value is absent
// OR unparseable. Bare Number('abc') is NaN, which would silently disable the upload
// guard (`size > NaN` is always false) and make setTimeout(…, NaN) fire immediately,
// aborting every request (audit F1). Exported so other env caps (e.g. the
// useAnalysis batch-frame mirror) reuse the same negative/zero/NaN handling.
export function positiveNumberEnv(raw, fallback) {
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

const MAX_UPLOAD_BYTES =
  positiveNumberEnv(import.meta.env.VITE_PAPI_MAX_UPLOAD_MB, DEFAULT_MAX_UPLOAD_MB) * 1024 * 1024
const REQUEST_TIMEOUT_MS = positiveNumberEnv(
  import.meta.env.VITE_PAPI_REQUEST_TIMEOUT_MS,
  DEFAULT_REQUEST_TIMEOUT_MS,
)
// Inference is sequential at ~0.4 fps, so a long video (up to 600 frames) or a
// folder batch (up to 200 images) can legitimately run for many minutes — far
// past the 60s GET timeout. The three analyze calls get their own generous budget
// so the headline video/batch features aren't aborted mid-analysis (audit H2).
const DEFAULT_ANALYZE_TIMEOUT_MS = 30 * 60_000
const ANALYZE_TIMEOUT_MS = positiveNumberEnv(
  import.meta.env.VITE_PAPI_ANALYZE_TIMEOUT_MS,
  DEFAULT_ANALYZE_TIMEOUT_MS,
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
async function fetchWithTimeout(input, init = {}, timeoutMs = REQUEST_TIMEOUT_MS, externalSignal) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  // An optional caller-supplied signal lets the UI CANCEL an in-flight request — e.g.
  // a Live-Demo run superseded by a newer upload. Without it the old request keeps
  // running server-side, logs a History row, and writes an annotated artifact for a
  // result the UI has already discarded (audit P2: stale backend requests).
  const onExternalAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', onExternalAbort, { once: true })
  }
  try {
    // no-store: API responses (logs, stats, model) must never be served from
    // the browser HTTP cache, or the History "Refresh" button could re-render
    // stale rows after a new analysis was logged.
    return await fetch(input, { ...init, cache: 'no-store', signal: controller.signal })
  } catch (error) {
    if (error?.name === 'AbortError') {
      // A caller-driven cancel (newer run/upload) is not a timeout — surface it as a
      // distinct, quietly-ignorable error so the stale-run guard drops it without the
      // misleading "backend didn't respond" message.
      if (externalSignal?.aborted) {
        throw new Error('Request superseded by a newer analysis.', { cause: error })
      }
      // Attach the original AbortError as the cause so devtools / Sentry
      // / future error boundaries can inspect both layers (preserve-caught-error).
      // The message stays English for the console; display sites localize via
      // the code + timeoutSeconds through localizedErrorMessage().
      const timeoutError = new Error(
        `Backend did not respond within ${Math.round(timeoutMs / 1000)} s. The request may still finish server-side — refresh logs to verify.`,
        { cause: error },
      )
      timeoutError.code = REQUEST_TIMEOUT_ERROR_CODE
      timeoutError.timeoutSeconds = Math.round(timeoutMs / 1000)
      throw timeoutError
    }
    throw error
  } finally {
    window.clearTimeout(timer)
    if (externalSignal) externalSignal.removeEventListener('abort', onExternalAbort)
  }
}

/**
 * Parse a successful response body, turning a malformed/truncated payload into a
 * clean, actionable rejection instead of an opaque "Unexpected end of JSON input"
 * (or similar) escaping as an unhandled throw. Callers have already checked
 * `response.ok`, so a parse failure here means the backend sent a 2xx with a body
 * we can't read — surface that distinctly (audit: guard the ok-path parse).
 */
/**
 * Flatten a backend error `detail` into a readable message. FastAPI validation
 * errors (422) carry an ARRAY of {loc, msg} objects — rendering that raw turns
 * the banner into "[object Object]" (user test 2026-06-11, non-numeric drone
 * telemetry). Strings pass through; anything unusable falls back.
 */
function detailToMessage(detail, fallback) {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => {
        if (typeof entry === 'string') return entry
        if (!entry?.msg) return null
        const field = Array.isArray(entry.loc) ? entry.loc[entry.loc.length - 1] : null
        return field ? `${field}: ${entry.msg}` : entry.msg
      })
      .filter(Boolean)
    if (parts.length) return parts.join(' · ')
  }
  return fallback
}

async function parseJsonBody(response, label) {
  try {
    return await response.json()
  } catch (error) {
    throw new Error(`${label} returned a malformed response body.`, { cause: error })
  }
}

export function mediaUrl(path) {
  if (!path) {
    return null
  }
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('blob:')) {
    return path
  }
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

/**
 * Resolve a backend artifact URL for display. When an API key is configured,
 * browser media tags cannot add X-API-Key, so fetch the artifact once and render
 * it through an object URL instead of a bare /media src.
 */
export async function resolveMediaUrl(path, signal) {
  const url = mediaUrl(path)
  if (!url || !API_KEY || url.startsWith('blob:')) {
    return url
  }

  const response = await fetchWithTimeout(url, { headers: buildHeaders() }, REQUEST_TIMEOUT_MS, signal)
  if (!response.ok) {
    throw new Error(`Could not load media artifact (${response.status})`)
  }

  try {
    const blob = await response.blob()
    return URL.createObjectURL(blob)
  } catch (error) {
    throw new Error('Media artifact returned a malformed response body.', { cause: error })
  }
}

export function revokeMediaUrl(url) {
  if (url?.startsWith('blob:')) {
    URL.revokeObjectURL(url)
  }
}

/**
 * Readiness probe for the topbar status cell. Deliberately cheap: short
 * timeout (a hung backend should read as offline within seconds, not after
 * the full 60s request budget) and a boolean result — callers only need
 * online / offline, never the body.
 */
export async function fetchHealth(signal) {
  try {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/health`,
      { headers: buildHeaders() },
      5_000,
      signal,
    )
    return response.ok
  } catch {
    return false
  }
}

export async function fetchRunways() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/runways`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load runways (${response.status})`)
  }
  return parseJsonBody(response, 'Runways')
}

/**
 * Register a runway the model can score against. ``payload`` is
 * { label, id?, airport?, designation?, lights: [{point, latitude, longitude, altitude_m} x4] }.
 * Surfaces the backend's validation message (422 detail can be a list) so the
 * Runways form can show "A runway must have exactly 4 PAPI lamps." etc.
 */
export async function createRunway(payload) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/runways`, {
    method: 'POST',
    headers: buildHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    let detail = `Could not create runway (${response.status})`
    try {
      const body = await response.json()
      detail = detailToMessage(body.detail, detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
  return parseJsonBody(response, 'Runway')
}

/** Delete a custom runway (built-ins are 400, unknown ids 404). 204 on success. */
export async function deleteRunway(runwayId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/runways/${encodeURIComponent(runwayId)}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
  if (!response.ok) {
    let detail = `Could not delete runway (${response.status})`
    try {
      const body = await response.json()
      detail = detailToMessage(body.detail, detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }
}

export async function fetchModelInfo(modelId) {
  // No id -> the backend default's card; with an id -> that registry entry's
  // card (provenance + val_metrics), powering the Insights per-model view.
  const query = modelId ? `?model_id=${encodeURIComponent(modelId)}` : ''
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/model${query}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load model info (${response.status})`)
  }
  return parseJsonBody(response, 'Model info')
}

export async function fetchModels() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/models`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    // This failure renders inside the model selector's live region, but api.js has no
    // i18n access — throw a typed code and let useAnalysis map it to the active
    // locale's message. The English message stays for devtools/console only.
    const error = new Error(`Could not load model options (${response.status})`)
    error.code = MODEL_OPTIONS_ERROR_CODE
    throw error
  }
  return parseJsonBody(response, 'Model options')
}

// Stable error code for a failed /api/models load — the UI layer owns the translation.
export const MODEL_OPTIONS_ERROR_CODE = 'model-options-unavailable'

export async function fetchStats(options = {}) {
  // Same camelCase filter set as fetchLogs/logsCsvUrl (limit/offset are simply
  // absent here) — the backend aggregates the matching slice (History stats cards).
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/stats${buildLogQuery(options)}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load inference stats (${response.status})`)
  }
  return parseJsonBody(response, 'Inference stats')
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
  modelId,
} = {}) {
  const params = new URLSearchParams()
  if (limit != null) params.set('limit', String(limit))
  if (offset != null) params.set('offset', String(offset))
  if (runwayId) params.set('runway_id', runwayId)
  if (mediaType) params.set('media_type', mediaType)
  if (globalState) params.set('global_state', globalState)
  if (createdAfter) params.set('created_after', createdAfter)
  if (minConfidence != null && minConfidence !== '') params.set('min_confidence', String(minConfidence))
  if (modelId) params.set('model_id', modelId)
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
  const data = await parseJsonBody(response, 'Analysis history')
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
  let blob
  try {
    blob = await response.blob()
  } catch (error) {
    throw new Error('Log export returned a malformed response body.', { cause: error })
  }
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
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/logs/${encodeURIComponent(logId)}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Could not load analysis ${logId} (${response.status})`)
  }
  return parseJsonBody(response, `Analysis ${logId}`)
}

async function parseAnalysisResponse(response) {
  if (!response.ok) {
    let detail = `Analysis failed (${response.status})`
    try {
      const body = await response.json()
      detail = detailToMessage(body.detail, detail)
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }

  return parseJsonBody(response, 'Analysis')
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
    // Omitted when null/empty (no registry entry selected yet, or /api/models failed)
    // so the backend applies its own default model instead of rejecting an invented id.
    model_id: metadata.modelId,
  }
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== '') {
      formData.append(key, value)
    }
  }
}

/**
 * Attach an optional drone-telemetry file (DJI .SRT / CSV / JSON) to the request.
 * The backend parses it into drone fixes that take priority over manual telemetry
 * and the media's embedded EXIF — for a video this yields a per-frame angle track.
 * A falsy `metadataFile` appends nothing, so the existing EXIF/manual paths are
 * untouched when no file was chosen.
 */
function appendMetadataFile(formData, metadataFile) {
  if (metadataFile) {
    formData.append('metadata_file', metadataFile, metadataFile.name)
  }
}

export async function analyzeFrame(file, metadata, metadataFile, signal) {
  checkUploadSize(file)
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)
  appendMetadataFile(formData, metadataFile)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze-frame`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
    signal,
  )

  return parseAnalysisResponse(response)
}

export async function analyzeFrames(files, metadata, metadataFile, signal) {
  checkUploadSize(files)
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  appendMetadata(formData, metadata)
  appendMetadataFile(formData, metadataFile)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze-frames`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
    signal,
  )

  return parseAnalysisResponse(response)
}

/**
 * Analyse a folder of images as ONE time-sequenced video: the backend stitches
 * the frames through the same ByteTrack + transition pipeline as a real video
 * and returns a single AnalysisPayload (not a per-image batch like analyzeFrames).
 * Files keep their folder paths so the backend can order them by capture sequence.
 */
export async function analyzeSequence(files, metadata, metadataFile, signal) {
  checkUploadSize(files)
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  appendMetadata(formData, metadata)
  appendMetadataFile(formData, metadataFile)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze-sequence`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
    signal,
  )

  return parseAnalysisResponse(response)
}

export async function analyzeMedia(file, metadata, metadataFile, signal) {
  checkUploadSize(file)
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)
  appendMetadataFile(formData, metadataFile)

  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/analyze`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
    signal,
  )

  return parseAnalysisResponse(response)
}
