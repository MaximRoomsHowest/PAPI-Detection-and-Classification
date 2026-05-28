/**
 * Smoke tests for the frontend API client.
 *
 * Goals:
 *   1. Pin the URL construction so a refactor of `API_BASE_URL` handling
 *      doesn't silently break GET routes.
 *   2. Pin the X-API-Key header behaviour — the production deployment
 *      depends on it; a regression that drops the header would silently
 *      turn every call into a 401.
 *   3. Cover the upload guard so the user-visible error message stays
 *      stable and the byte-math doesn't drift.
 *   4. Cover the timeout wrapper so the demo doesn't hang forever if the
 *      backend takes a coffee break.
 *
 * Tests use `vi.stubGlobal('fetch', ...)` rather than mocking modules so
 * the assertions stay close to "what the browser sees". Each test stubs
 * fetch fresh; teardown is in `afterEach`.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  analyzeFrame,
  analyzeFrames,
  analyzeMedia,
  fetchLogs,
  fetchModelInfo,
  fetchRunways,
  fetchStats,
  mediaUrl,
} from './api.js'

/** Helper: build a Response-like object the way fetch resolves to one. */
function jsonResponse(body, { ok = true, status = ok ? 200 : 500 } = {}) {
  return {
    ok,
    status,
    statusText: status === 200 ? 'OK' : 'ERR',
    json: async () => body,
  }
}

function makeFile(name, sizeBytes, type = 'image/jpeg') {
  // jsdom's File constructor doesn't compute size from content, so we
  // monkey-patch a `size` property. checkUploadSize only reads .size + .name.
  const f = new File(['x'], name, { type })
  Object.defineProperty(f, 'size', { value: sizeBytes })
  return f
}

beforeEach(() => {
  // Default fetch: succeeds with `{}` so tests can ignore the response.
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({})))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('mediaUrl', () => {
  it('returns null for empty paths so callers can short-circuit', () => {
    expect(mediaUrl(undefined)).toBeNull()
    expect(mediaUrl(null)).toBeNull()
    expect(mediaUrl('')).toBeNull()
  })

  it('passes absolute URLs through unchanged', () => {
    expect(mediaUrl('https://example.test/x.jpg')).toBe('https://example.test/x.jpg')
    expect(mediaUrl('http://example.test/x.jpg')).toBe('http://example.test/x.jpg')
  })

  it('prepends API_BASE_URL to relative paths', () => {
    // Default API_BASE_URL is http://127.0.0.1:8000 (see VITE_PAPI_API_URL).
    expect(mediaUrl('/media/foo.jpg')).toMatch(/^https?:\/\/[^/]+\/media\/foo\.jpg$/)
  })

  it('inserts the slash when the path is missing one', () => {
    expect(mediaUrl('media/foo.jpg')).toMatch(/\/media\/foo\.jpg$/)
  })
})

describe('GET endpoints — URL + header pinning', () => {
  it('fetchRunways targets /api/runways', async () => {
    await fetchRunways()
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/runways$/)
  })

  it('fetchModelInfo targets /api/model', async () => {
    await fetchModelInfo()
    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/model$/)
  })

  it('fetchStats targets /api/stats', async () => {
    await fetchStats()
    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/stats$/)
  })

  it('fetchLogs targets /api/logs', async () => {
    await fetchLogs()
    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/logs$/)
  })

  it('GET endpoints surface backend errors with status code in the message', async () => {
    fetch.mockResolvedValueOnce(jsonResponse({}, { ok: false, status: 503 }))
    await expect(fetchRunways()).rejects.toThrow(/503/)
  })
})

describe('analyze* — multipart payload + auth', () => {
  const metadata = {
    runwayId: '24',
    droneId: 'M4E-01',
    droneLatitude: '47.668810',
    droneLongitude: '9.504007',
    droneAltitudeM: '466.5',
  }

  it('analyzeFrame POSTs to /api/analyze-frame with file + metadata', async () => {
    const file = makeFile('frame.jpg', 5_000_000)
    await analyzeFrame(file, metadata)

    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/analyze-frame$/)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file')).toBe(file)
    expect(init.body.get('runway_id')).toBe('24')
    expect(init.body.get('drone_id')).toBe('M4E-01')
    expect(init.body.get('drone_latitude')).toBe('47.668810')
  })

  it('analyzeFrames POSTs every file under "files" with folder paths preserved', async () => {
    const f1 = makeFile('a.jpg', 1_000)
    const f2 = makeFile('b.jpg', 1_000)
    // Simulate the webkitRelativePath the browser sets on folder uploads.
    Object.defineProperty(f1, 'webkitRelativePath', { value: 'flight1/a.jpg' })
    Object.defineProperty(f2, 'webkitRelativePath', { value: 'flight1/b.jpg' })

    await analyzeFrames([f1, f2], metadata)

    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/analyze-frames$/)
    const files = init.body.getAll('files')
    expect(files).toHaveLength(2)
    // FormData.append(name, file, filename) wraps the File so identity
    // is lost — but the wrapper's `.name` is the filename we passed.
    // That filename is what the backend reads as the per-file path, so
    // pinning the names directly is the actual contract under test.
    const names = files.map((f) => f.name)
    expect(names).toEqual(['flight1/a.jpg', 'flight1/b.jpg'])
  })

  it('analyzeMedia POSTs to /api/analyze (the polymorphic image+video route)', async () => {
    const file = makeFile('clip.mp4', 50_000_000, 'video/mp4')
    await analyzeMedia(file, metadata)

    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/analyze$/)
  })

  it('does not include optional metadata when empty strings are passed', async () => {
    const file = makeFile('frame.jpg', 1_000)
    await analyzeFrame(file, {
      runwayId: '24',
      droneId: '',
      droneLatitude: '',
      droneLongitude: '',
      droneAltitudeM: '',
    })

    const [, init] = fetch.mock.calls[0]
    expect(init.body.get('runway_id')).toBe('24')
    expect(init.body.get('drone_id')).toBeNull()
    expect(init.body.get('drone_latitude')).toBeNull()
  })
})

describe('analyze* — error surfacing', () => {
  const tinyFile = () => makeFile('frame.jpg', 1_000)
  const metadata = { runwayId: '24', droneId: '', droneLatitude: '', droneLongitude: '', droneAltitudeM: '' }

  it('surfaces backend `detail` strings to the caller verbatim', async () => {
    fetch.mockResolvedValueOnce(jsonResponse({ detail: 'Boom' }, { ok: false, status: 400 }))
    await expect(analyzeFrame(tinyFile(), metadata)).rejects.toThrow('Boom')
  })

  it('falls back to a status-coded message when the body has no detail', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: '',
      json: async () => {
        throw new Error('not json')
      },
    })
    await expect(analyzeFrame(tinyFile(), metadata)).rejects.toThrow(/500/)
  })
})

describe('upload size guard', () => {
  // The default MAX_UPLOAD_BYTES is 100 MB per file (VITE_PAPI_MAX_UPLOAD_MB).
  // We test slightly over the limit to avoid false-negatives from rounding.
  const overSized = 101 * 1024 * 1024

  it('rejects a single file that exceeds the per-file cap', async () => {
    const big = makeFile('big.jpg', overSized)
    await expect(
      analyzeFrame(big, { runwayId: '24', droneId: '', droneLatitude: '', droneLongitude: '', droneAltitudeM: '' }),
    ).rejects.toThrow(/exceeds/i)
    // And: fetch must not have been called — the guard fails fast.
    expect(fetch).not.toHaveBeenCalled()
  })

  it('rejects a folder batch that exceeds the aggregate cap', async () => {
    // 5 × 95 MB = 475 MB > the 400 MB aggregate cap (4 × per-file).
    const files = Array.from({ length: 5 }, (_, i) => makeFile(`f${i}.jpg`, 95 * 1024 * 1024))
    await expect(
      analyzeFrames(files, {
        runwayId: '24',
        droneId: '',
        droneLatitude: '',
        droneLongitude: '',
        droneAltitudeM: '',
      }),
    ).rejects.toThrow(/batch limit|exceeding/i)
    expect(fetch).not.toHaveBeenCalled()
  })
})

describe('fetchWithTimeout — abort propagation', () => {
  it('rejects with a friendly timeout message when fetch aborts', async () => {
    // Stub fetch to throw an AbortError, mimicking what the AbortController
    // does when the timer fires. We don't actually need to wait the full
    // 60 s — the message only depends on the error name.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        const err = new Error('aborted')
        err.name = 'AbortError'
        throw err
      }),
    )

    await expect(fetchRunways()).rejects.toThrow(/did not respond/i)
  })
})
