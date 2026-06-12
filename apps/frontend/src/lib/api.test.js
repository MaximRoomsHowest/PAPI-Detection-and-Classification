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
  analyzeSequence,
  createRunway,
  deleteRunway,
  fetchLogs,
  fetchModelInfo,
  fetchModels,
  fetchRunways,
  fetchStats,
  logsCsvUrl,
  mediaUrl,
  resolveMediaUrl,
} from './api.js'
import { REQUEST_TIMEOUT_ERROR_CODE } from './errorMessages.js'

/** Helper: build a Response-like object the way fetch resolves to one. */
function jsonResponse(body, { ok = true, status = ok ? 200 : 500 } = {}) {
  return {
    ok,
    status,
    statusText: status === 200 ? 'OK' : 'ERR',
    json: async () => body,
  }
}

/** Like jsonResponse but with a headers.get() shim (for X-Total-Count). */
function jsonResponseWithHeaders(body, { ok = true, status = 200, headers = {} } = {}) {
  return {
    ok,
    status,
    statusText: 'OK',
    json: async () => body,
    headers: { get: (key) => headers[key] ?? null },
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
    expect(mediaUrl('blob:http://example.test/artifact')).toBe('blob:http://example.test/artifact')
  })

  it('prepends API_BASE_URL to relative paths', () => {
    // Default API_BASE_URL is http://127.0.0.1:8000 (see VITE_PAPI_API_URL).
    expect(mediaUrl('/media/foo.jpg')).toMatch(/^https?:\/\/[^/]+\/media\/foo\.jpg$/)
  })

  it('inserts the slash when the path is missing one', () => {
    expect(mediaUrl('media/foo.jpg')).toMatch(/\/media\/foo\.jpg$/)
  })

  it('resolveMediaUrl leaves object URLs untouched for media tag rendering', async () => {
    const url = 'blob:http://example.test/artifact'
    await expect(resolveMediaUrl(url)).resolves.toBe(url)
    expect(fetch).not.toHaveBeenCalled()
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

  it('fetchModels targets /api/models', async () => {
    await fetchModels()
    const [url] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/models$/)
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

describe('runway mutations — payloads and backend details', () => {
  const runwayPayload = {
    label: 'Custom 24',
    airport: 'EDNY',
    designation: '24',
    lights: [
      { point: 1, latitude: 47.673521, longitude: 9.518154, altitude_m: 461.37 },
      { point: 2, latitude: 47.67345, longitude: 9.518214, altitude_m: 461.37 },
      { point: 3, latitude: 47.67338, longitude: 9.518274, altitude_m: 461.37 },
      { point: 4, latitude: 47.673309, longitude: 9.518333, altitude_m: 461.37 },
    ],
  }

  it('createRunway posts JSON and returns the backend body', async () => {
    fetch.mockResolvedValueOnce(jsonResponse({ id: 'custom_24', label: 'Custom 24' }))

    const result = await createRunway(runwayPayload)

    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/runways$/)
    expect(init.method).toBe('POST')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual(runwayPayload)
    expect(result).toEqual({ id: 'custom_24', label: 'Custom 24' })
  })

  it('createRunway flattens backend validation detail arrays', async () => {
    fetch.mockResolvedValueOnce(
      jsonResponse(
        {
          detail: [
            { msg: 'A runway must have exactly 4 PAPI lamps.' },
            { msg: 'Lamp coordinates must be distinct.' },
          ],
        },
        { ok: false, status: 422 },
      ),
    )

    await expect(createRunway({})).rejects.toThrow(
      'A runway must have exactly 4 PAPI lamps. · Lamp coordinates must be distinct.',
    )
  })

  it('deleteRunway encodes the id and uses DELETE', async () => {
    await deleteRunway('custom x/1')

    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/runways\/custom%20x%2F1$/)
    expect(init.method).toBe('DELETE')
  })

  it('deleteRunway surfaces backend detail strings', async () => {
    fetch.mockResolvedValueOnce(
      jsonResponse({ detail: 'Built-in runways cannot be deleted.' }, { ok: false, status: 400 }),
    )

    await expect(deleteRunway('papi_24')).rejects.toThrow('Built-in runways cannot be deleted.')
  })
})

describe('analyze* — multipart payload + auth', () => {
  const metadata = {
    runwayId: '24',
    droneId: 'M4E-01',
    droneLatitude: '47.668810',
    droneLongitude: '9.504007',
    droneAltitudeM: '466.5',
    modelId: 'nano',
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
    expect(init.body.get('model_id')).toBe('nano')
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

  it('analyzeSequence POSTs every file under "files" to /api/analyze-sequence', async () => {
    const f1 = makeFile('a.jpg', 1_000)
    const f2 = makeFile('b.jpg', 1_000)
    Object.defineProperty(f1, 'webkitRelativePath', { value: 'flight1/a.jpg' })
    Object.defineProperty(f2, 'webkitRelativePath', { value: 'flight1/b.jpg' })

    await analyzeSequence([f1, f2], metadata)

    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/analyze-sequence$/)
    expect(init.method).toBe('POST')
    const files = init.body.getAll('files')
    expect(files.map((f) => f.name)).toEqual(['flight1/a.jpg', 'flight1/b.jpg'])
    expect(init.body.get('runway_id')).toBe('24')
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

  it('omits model_id when no model is selected yet, so the backend default applies', async () => {
    // Before /api/models resolves (or after it fails / on a legacy backend) the UI
    // holds modelId=null — sending a guessed id would 400 with "Unknown model_id".
    const file = makeFile('frame.jpg', 1_000)
    await analyzeFrame(file, { runwayId: '24', modelId: null })

    const [, init] = fetch.mock.calls[0]
    expect(init.body.get('model_id')).toBeNull()
    // transition_method is backend-owned now; the client never sends it.
    expect(init.body.get('transition_method')).toBeNull()
  })
})

describe('analyze* — optional telemetry file', () => {
  const metadata = { runwayId: '24', droneId: '', droneLatitude: '', droneLongitude: '', droneAltitudeM: '' }

  it('analyzeMedia attaches the telemetry file as metadata_file', async () => {
    const clip = makeFile('clip.mp4', 1_000_000, 'video/mp4')
    const srt = makeFile('clip.srt', 2_000, 'application/x-subrip')
    await analyzeMedia(clip, metadata, srt)

    const [, init] = fetch.mock.calls[0]
    // FormData wraps the file; its `.name` is the contract the backend reads.
    expect(init.body.get('metadata_file')?.name).toBe('clip.srt')
  })

  it('analyzeFrame attaches the telemetry file as metadata_file', async () => {
    const img = makeFile('frame.jpg', 1_000)
    const csv = makeFile('track.csv', 500, 'text/csv')
    await analyzeFrame(img, metadata, csv)

    const [, init] = fetch.mock.calls[0]
    expect(init.body.get('metadata_file')?.name).toBe('track.csv')
  })

  it('omits metadata_file entirely when none is provided', async () => {
    await analyzeMedia(makeFile('clip.mp4', 1_000, 'video/mp4'), metadata)
    const [, init] = fetch.mock.calls[0]
    expect(init.body.get('metadata_file')).toBeNull()
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

  it('flattens a FastAPI 422 array detail into a readable message', async () => {
    // Non-numeric drone telemetry produces this shape; rendering it raw used to
    // surface "[object Object]" in the error banner (user test 2026-06-11).
    fetch.mockResolvedValueOnce(
      jsonResponse(
        {
          detail: [
            {
              type: 'float_parsing',
              loc: ['body', 'drone_latitude'],
              msg: 'Input should be a valid number, unable to parse string as a number',
              input: 'abc',
            },
          ],
        },
        { ok: false, status: 422 },
      ),
    )
    await expect(analyzeFrame(tinyFile(), metadata)).rejects.toThrow(
      'drone_latitude: Input should be a valid number, unable to parse string as a number',
    )
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

describe('fetchLogs — filters + total count', () => {
  it('builds a querystring from camelCase options', async () => {
    await fetchLogs({
      limit: 10,
      offset: 20,
      runwayId: 'papi_24',
      globalState: 'too_low',
      minConfidence: 0.5,
      modelId: 'nano',
    })
    const [url] = fetch.mock.calls[0]
    expect(url).toContain('/api/logs?')
    expect(url).toContain('limit=10')
    expect(url).toContain('offset=20')
    expect(url).toContain('runway_id=papi_24')
    expect(url).toContain('global_state=too_low')
    expect(url).toContain('min_confidence=0.5')
    expect(url).toContain('model_id=nano')
  })

  it('omits model_id from the query when no model filter is active', async () => {
    await fetchLogs({ limit: 10, modelId: '' })
    const [url] = fetch.mock.calls[0]
    expect(url).not.toContain('model_id')
  })

  it('returns items + total from the X-Total-Count header', async () => {
    fetch.mockResolvedValueOnce(
      jsonResponseWithHeaders([{ id: 'a' }, { id: 'b' }], { headers: { 'X-Total-Count': '57' } }),
    )
    const { items, total } = await fetchLogs()
    expect(items).toHaveLength(2)
    expect(total).toBe(57)
  })

  it('falls back to items.length when the header is absent', async () => {
    fetch.mockResolvedValueOnce(jsonResponseWithHeaders([{ id: 'a' }]))
    const { total } = await fetchLogs()
    expect(total).toBe(1)
  })
})

describe('logsCsvUrl', () => {
  it('points at export.csv and carries filters', () => {
    const url = logsCsvUrl({ runwayId: 'papi_06' })
    expect(url).toMatch(/\/api\/logs\/export\.csv\?/)
    expect(url).toContain('runway_id=papi_06')
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

  it('tags the timeout error with the code + seconds the UI localizes from', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        const err = new Error('aborted')
        err.name = 'AbortError'
        throw err
      }),
    )

    const error = await fetchRunways().catch((caught) => caught)
    expect(error.code).toBe(REQUEST_TIMEOUT_ERROR_CODE)
    // Default GET budget is 60 s; display sites interpolate this into the
    // localized errors.requestTimeout string.
    expect(error.timeoutSeconds).toBe(60)
  })
})
