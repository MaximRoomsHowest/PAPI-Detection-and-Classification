const API_BASE_URL = (import.meta.env.VITE_PAPI_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const API_KEY = import.meta.env.VITE_PAPI_API_KEY

function buildHeaders(extra = {}) {
  const headers = { ...extra }
  if (API_KEY) {
    headers['X-API-Key'] = API_KEY
  }
  return headers
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
  const response = await fetch(`${API_BASE_URL}/api/runways`, {
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
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)

  const response = await fetch(`${API_BASE_URL}/api/analyze-frame`, {
    method: 'POST',
    headers: buildHeaders(),
    body: formData,
  })

  return parseAnalysisResponse(response)
}

export async function analyzeFrames(files, metadata) {
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file, file.webkitRelativePath || file.name)
  })
  appendMetadata(formData, metadata)

  const response = await fetch(`${API_BASE_URL}/api/analyze-frames`, {
    method: 'POST',
    headers: buildHeaders(),
    body: formData,
  })

  return parseAnalysisResponse(response)
}

export async function analyzeMedia(file, metadata) {
  const formData = new FormData()
  formData.append('file', file)
  appendMetadata(formData, metadata)

  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: 'POST',
    headers: buildHeaders(),
    body: formData,
  })

  return parseAnalysisResponse(response)
}
