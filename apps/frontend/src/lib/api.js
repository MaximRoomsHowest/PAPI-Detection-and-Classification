import { REQUEST_TIMEOUT_ERROR_CODE } from './errorMessages'

const API_BASE_URL = (import.meta.env.VITE_PAPI_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const ENV_API_KEY = import.meta.env.VITE_PAPI_API_KEY

export const AUTH_SESSION_STORAGE = 'papi.authSession.v1'

// localStorage slot for a RUNTIME admin key. A deployed read-only demo can keep
// the management UI hidden until an operator pastes the key here; it is preferred
// over the build-time VITE_PAPI_API_KEY so an operator can unlock without a rebuild.
export const ADMIN_KEY_STORAGE = 'papi.adminKey'

function readJsonStorage(key) {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function removeStorage(key) {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* accept the loss for this session */
  }
}

export function getAuthSession() {
  const session = readJsonStorage(AUTH_SESSION_STORAGE)
  if (!session?.access_token) return null
  if (Number.isFinite(session.expires_at) && session.expires_at * 1000 <= Date.now()) {
    removeStorage(AUTH_SESSION_STORAGE)
    return null
  }
  return session
}

export function setAuthSession(session) {
  try {
    if (session?.access_token) {
      window.localStorage.setItem(
        AUTH_SESSION_STORAGE,
        JSON.stringify({
          access_token: session.access_token,
          token_type: session.token_type || 'bearer',
          expires_at: session.expires_at,
          user: session.user || null,
        }),
      )
    } else {
      window.localStorage.removeItem(AUTH_SESSION_STORAGE)
    }
  } catch {
    /* accept the loss for this session */
  }
}

export function clearAuthSession() {
  setAuthSession(null)
}

export function getApiKey() {
  try {
    const stored = window.localStorage.getItem(ADMIN_KEY_STORAGE)
    if (stored) return stored
  } catch {
    /* localStorage unavailable (private mode/SSR) — fall back to the env key. */
  }
  return ENV_API_KEY || null
}

/** Store (or clear, when falsy) the runtime admin key. */
export function setAdminKey(key) {
  const trimmed = (key || '').trim()
  try {
    if (trimmed) window.localStorage.setItem(ADMIN_KEY_STORAGE, trimmed)
    else window.localStorage.removeItem(ADMIN_KEY_STORAGE)
  } catch {
    /* accept the loss for this session */
  }
}

export function hasApiKeyConfigured() {
  return Boolean(getApiKey())
}

// Timeout guards (audit F-MAJ-8) are genuinely client-side concerns, so they stay env-
// configurable at build time. Upload SIZE/COUNT limits, however, mirror the backend and
// are fetched at runtime from /api/limits (see refreshUploadLimits) so the backend env is
// the single source of truth — changing PAPI_MAX_* in .env propagates here without a
// rebuild, instead of duplicating the value in a baked VITE_PAPI_MAX_* constant.
const DEFAULT_REQUEST_TIMEOUT_MS = 60_000

// Parse a numeric env override, falling back to the default when the value is absent
// OR unparseable. Bare Number('abc') is NaN, which would make setTimeout(…, NaN) fire
// immediately, aborting every request (audit F1).
export function positiveNumberEnv(raw, fallback) {
  const value = Number(raw)
  return Number.isFinite(value) && value > 0 ? value : fallback
}

// Client-side upload guards mirror the BACKEND's PAPI_MAX_* env (single source of truth),
// fetched once at app start via refreshUploadLimits(). Until that resolves they are no-ops
// (Infinity): the backend still enforces and returns a clear 413, so nothing is wrongly
// rejected before the limits load. The guards exist only for fast, friendly pre-checks.
let clientLimits = {
  maxUploadBytes: Infinity,
  maxBatchUploadBytes: Infinity,
  maxBatchFrames: Infinity,
}

export function getClientLimits() {
  return clientLimits
}

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
  const session = getAuthSession()
  if (session?.access_token) {
    headers.Authorization = `Bearer ${session.access_token}`
    return headers
  }
  const key = getApiKey()
  if (key) {
    headers['X-API-Key'] = key
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
  // Both caps come from the backend (the single source) via refreshUploadLimits.
  const { maxUploadBytes, maxBatchUploadBytes } = clientLimits
  const fileList = Array.isArray(files) ? files : [files]
  let totalBytes = 0
  for (const file of fileList) {
    if (!file || typeof file.size !== 'number') continue
    if (file.size > maxUploadBytes) {
      throw new Error(
        `File "${file.name}" is ${formatBytes(file.size)}, which exceeds the ${formatBytes(maxUploadBytes)} per-file limit. Compress or trim the file before uploading.`,
      )
    }
    totalBytes += file.size
  }
  // Folder uploads can be many files at once; cap aggregate size too.
  if (fileList.length > 1 && totalBytes > maxBatchUploadBytes) {
    throw new Error(
      `Folder upload totals ${formatBytes(totalBytes)} across ${fileList.length} files, exceeding the ${formatBytes(maxBatchUploadBytes)} batch limit.`,
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
 * Resolve a backend artifact URL for display. Browser media tags cannot add
 * Authorization or X-API-Key headers, so fetch protected artifacts once and
 * render them through object URLs instead of bare /media src values.
 */
export async function resolveMediaUrl(path, signal) {
  const url = mediaUrl(path)
  const hasRequestCredentials = Boolean(getAuthSession()?.access_token || getApiKey())
  if (!url || !hasRequestCredentials || url.startsWith('blob:')) {
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

export async function fetchAuthConfig() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/auth/config`)
  if (!response.ok) {
    throw new Error(`Could not load auth configuration (${response.status})`)
  }
  return parseJsonBody(response, 'Auth configuration')
}

export async function fetchCurrentUser() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/auth/me`, {
    headers: buildHeaders(),
  })
  if (!response.ok) {
    clearAuthSession()
    setAdminKey(null)
    throw new Error(`Could not verify auth session (${response.status})`)
  }
  return parseJsonBody(response, 'Current user')
}

export async function loginUser({ email, password }) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not sign in')
  const session = await parseJsonBody(response, 'Auth session')
  setAuthSession(session)
  setAdminKey(null)
  return session
}

export async function logoutUser() {
  try {
    await fetchWithTimeout(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: buildHeaders(),
    })
  } catch {
    /* Server-side logout is best-effort; local credentials are discarded below. */
  } finally {
    clearAuthSession()
    setAdminKey(null)
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

// Fetch the backend's upload limits and update the client-side guards in place. Called
// once at app start (see App). The backend env (PAPI_MAX_*) is the single source of
// truth; on any failure the prior (permissive) limits stay and the backend still enforces
// with a clear 413, so an upload is never wrongly blocked client-side.
export async function refreshUploadLimits() {
  try {
    const response = await fetchWithTimeout(`${API_BASE_URL}/api/limits`, { headers: buildHeaders() })
    if (!response.ok) return
    const body = await parseJsonBody(response, 'Upload limits')
    const toBytes = (mb) => (Number.isFinite(mb) && mb > 0 ? mb * 1024 * 1024 : Infinity)
    const toCount = (n) => (Number.isFinite(n) && n > 0 ? n : Infinity)
    clientLimits = {
      maxUploadBytes: toBytes(body.max_upload_mb),
      maxBatchUploadBytes: toBytes(body.max_batch_upload_mb),
      maxBatchFrames: toCount(body.max_batch_frames),
    }
  } catch {
    /* keep current limits; the backend remains the hard enforcer */
  }
}

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

// --------------------------------------------------------------------------- //
// Model lifecycle: upload / promote / disable / delete / evaluate            //
// --------------------------------------------------------------------------- //

/** Surface a backend error body (string or 422 list) as a readable message. */
async function errorFrom(response, fallbackLabel) {
  let detail = `${fallbackLabel} (${response.status})`
  try {
    const body = await response.json()
    detail = detailToMessage(body.detail, detail)
  } catch {
    detail = response.statusText || detail
  }
  return new Error(detail)
}

/** Upload a .pt/.onnx model file. Long timeout: checkpoints can be hundreds of MB. */
export async function uploadModel({ file, label, role = 'detector', description, makeDefault = false }) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('label', label)
  formData.append('role', role)
  if (description) formData.append('description', description)
  formData.append('make_default', makeDefault ? 'true' : 'false')
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/models`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
  )
  if (!response.ok) throw await errorFrom(response, 'Could not upload model')
  return parseJsonBody(response, 'Model')
}

export async function promoteModel(modelId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/models/${encodeURIComponent(modelId)}/promote`, {
    method: 'POST',
    headers: buildHeaders(),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not promote model')
  return parseJsonBody(response, 'Model')
}

export async function setModelDisabled(modelId, disabled) {
  const action = disabled ? 'disable' : 'enable'
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/models/${encodeURIComponent(modelId)}/${action}`,
    { method: 'POST', headers: buildHeaders() },
  )
  if (!response.ok) throw await errorFrom(response, `Could not ${action} model`)
  return parseJsonBody(response, 'Model')
}

export async function deleteModel(modelId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/models/${encodeURIComponent(modelId)}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not delete model')
}

export async function evaluateModel(modelId, { datasetId, split = 'test' }) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/models/${encodeURIComponent(modelId)}/evaluate`,
    {
      method: 'POST',
      headers: buildHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ dataset_id: datasetId, split }),
    },
  )
  if (!response.ok) throw await errorFrom(response, 'Could not start evaluation')
  return parseJsonBody(response, 'Job')
}

// --------------------------------------------------------------------------- //
// Datasets + assisted labeling                                                //
// --------------------------------------------------------------------------- //

export async function fetchDatasets() {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/datasets`, { headers: buildHeaders() })
  if (!response.ok) throw new Error(`Could not load datasets (${response.status})`)
  return parseJsonBody(response, 'Datasets')
}

export async function uploadDatasetBundle({ file, name }) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('name', name)
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/datasets`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
  )
  if (!response.ok) throw await errorFrom(response, 'Could not upload dataset')
  return parseJsonBody(response, 'Dataset')
}

export async function startAssistedLabeling({ files, name, modelId }) {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file, file.name))
  formData.append('name', name)
  formData.append('model_id', modelId)
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/datasets/assisted`,
    { method: 'POST', headers: buildHeaders(), body: formData },
    ANALYZE_TIMEOUT_MS,
  )
  if (!response.ok) throw await errorFrom(response, 'Could not start assisted labeling')
  return parseJsonBody(response, 'Assisted labeling')
}

export async function fetchCandidates(datasetId) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/datasets/${encodeURIComponent(datasetId)}/candidates`,
    { headers: buildHeaders() },
  )
  if (!response.ok) throw new Error(`Could not load candidates (${response.status})`)
  return parseJsonBody(response, 'Candidates')
}

export async function commitLabels(datasetId, images) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/datasets/${encodeURIComponent(datasetId)}/commit`,
    {
      method: 'POST',
      headers: buildHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ images }),
    },
  )
  if (!response.ok) throw await errorFrom(response, 'Could not commit labels')
  return parseJsonBody(response, 'Commit')
}

export async function deleteDataset(datasetId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/datasets/${encodeURIComponent(datasetId)}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not delete dataset')
}

/**
 * Fetch a staged dataset image as an object URL. The endpoint is api-key gated,
 * so a bare <img src> would 401 when a key is configured — fetch + blob instead.
 * Caller must revokeMediaUrl() the result.
 */
export async function fetchAuthedImageUrl(path, signal) {
  const url = mediaUrl(path)
  if (!url) return null
  const response = await fetchWithTimeout(url, { headers: buildHeaders() }, REQUEST_TIMEOUT_MS, signal)
  if (!response.ok) throw new Error(`Could not load image (${response.status})`)
  const blob = await response.blob()
  return URL.createObjectURL(blob)
}

// --------------------------------------------------------------------------- //
// Training launchers                                                          //
// --------------------------------------------------------------------------- //

export async function prepareTraining({ datasetId, baseModelId, name, hyperparams }) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/training/prepare`, {
    method: 'POST',
    headers: buildHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      dataset_id: datasetId,
      base_model_id: baseModelId || null,
      name: name || null,
      hyperparams,
    }),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not prepare training')
  return parseJsonBody(response, 'Training prepare')
}

/** Download a prepared training bundle (fetch + blob so X-API-Key is sent). */
export async function downloadTrainingBundle(jobId, filename) {
  const response = await fetchWithTimeout(
    `${API_BASE_URL}/api/training/${encodeURIComponent(jobId)}/bundle`,
    { headers: buildHeaders() },
    ANALYZE_TIMEOUT_MS,
  )
  if (!response.ok) throw await errorFrom(response, 'Could not download bundle')
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename || `papi-training-${jobId}.zip`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

// --------------------------------------------------------------------------- //
// Jobs                                                                         //
// --------------------------------------------------------------------------- //

export async function fetchJobs(options = {}) {
  const params = new URLSearchParams()
  if (options.kind) params.set('kind', options.kind)
  if (options.status) params.set('status', options.status)
  if (options.limit != null) params.set('limit', String(options.limit))
  const qs = params.toString()
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/jobs${qs ? `?${qs}` : ''}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) throw new Error(`Could not load jobs (${response.status})`)
  return parseJsonBody(response, 'Jobs')
}

export async function fetchJob(jobId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/jobs/${encodeURIComponent(jobId)}`, {
    headers: buildHeaders(),
  })
  if (!response.ok) throw new Error(`Could not load job (${response.status})`)
  return parseJsonBody(response, 'Job')
}

export async function cancelJob(jobId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: 'POST',
    headers: buildHeaders(),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not cancel job')
  return parseJsonBody(response, 'Job')
}

// Dismiss one finished/failed/cancelled job (backend 409s an active one — the UI
// only offers this on terminal rows). 204 No Content, so nothing is parsed back.
export async function deleteJob(jobId) {
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not dismiss job')
}

// Bulk-clear every finished job (optionally of one kind so the Models page clears
// only evaluate jobs and Datasets only its own). Returns { deleted }.
export async function clearFinishedJobs({ kind } = {}) {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  const response = await fetchWithTimeout(`${API_BASE_URL}/api/jobs${qs}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
  if (!response.ok) throw await errorFrom(response, 'Could not clear jobs')
  return parseJsonBody(response, 'Jobs')
}
