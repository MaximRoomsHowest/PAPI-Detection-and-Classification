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
async function fetchWithTimeout(input, init = {}) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    return await fetch(input, { ...init, signal: controller.signal })
  } catch (error) {
    if (error?.name === 'AbortError') {
      // Attach the original AbortError as the cause so devtools / Sentry
      // / future error boundaries can inspect both layers (preserve-caught-error).
      throw new Error(
        `Backend did not respond within ${Math.round(REQUEST_TIMEOUT_MS / 1000)} s. The request may still finish server-side — refresh logs to verify.`,
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

function appendMetadata(formData, metadata) {
  formData.append('runway_id', metadata.runwayId)

  if (metadata.droneId) {
    formData.append('drone_id', metadata.droneId)
  }
  if (metadata.droneLatitude !== '') {
    formData.append('drone_latitude', metadata.droneLatitude)
  }
  if (metadata.droneLongitude !== '') {
    formData.append('drone_longitude', metadata.droneLongitude)
  }
  if (metadata.droneAltitudeM !== '') {
    formData.append('drone_altitude_m', metadata.droneAltitudeM)
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

export async function analyzeFrame(file, metadata) {
  checkUploadSize(file)
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)

  const response = await fetchWithTimeout(`${API_BASE_URL}/api/analyze-frame`, {
    method: 'POST',
    headers: buildHeaders(),
    body: formData,
  })

  return parseAnalysisResponse(response)
}

export async function analyzeFrames(files, metadata) {
  checkUploadSize(files)
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  appendMetadata(formData, metadata)

  const response = await fetchWithTimeout(`${API_BASE_URL}/api/analyze-frames`, {
    method: 'POST',
    headers: buildHeaders(),
    body: formData,
  })

  return parseAnalysisResponse(response)
}

export async function analyzeMedia(file, metadata) {
  checkUploadSize(file)
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)

  const response = await fetchWithTimeout(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: buildHeaders(),
    body: formData,
  })

  return parseAnalysisResponse(response)
}
