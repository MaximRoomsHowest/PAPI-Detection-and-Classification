/**
 * Tests for the model-lifecycle API client (upload / promote / evaluate /
 * datasets / jobs) and the runtime admin-key plumbing. Mirrors api.test.js:
 * stub global fetch, assert URL + method + headers + body the browser sends.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ADMIN_KEY_STORAGE,
  AUTH_SESSION_STORAGE,
  cancelJob,
  commitLabels,
  fetchAuthConfig,
  fetchCurrentUser,
  deleteModel,
  evaluateModel,
  fetchDatasets,
  fetchJob,
  getApiKey,
  getAuthSession,
  loginUser,
  logoutUser,
  resolveMediaUrl,
  setAuthSession,
  promoteModel,
  setAdminKey,
  uploadModel,
} from './api.js'

function jsonResponse(body, { ok = true, status = ok ? 200 : 500, statusText = 'OK' } = {}) {
  return { ok, status, statusText, json: async () => body }
}

function blobResponse(body = 'artifact-bytes', { ok = true, status = 200 } = {}) {
  return { ok, status, blob: async () => new Blob([body]) }
}

let fetchMock

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  window.localStorage.removeItem(ADMIN_KEY_STORAGE)
  window.localStorage.removeItem(AUTH_SESSION_STORAGE)
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.removeItem(ADMIN_KEY_STORAGE)
  window.localStorage.removeItem(AUTH_SESSION_STORAGE)
})

describe('admin key plumbing', () => {
  it('prefers the runtime admin key over the env key and clears it', () => {
    expect(getApiKey()).toBeFalsy()
    setAdminKey('secret-key')
    expect(getApiKey()).toBe('secret-key')
    setAdminKey(null)
    expect(getApiKey()).toBeFalsy()
  })

  it('attaches X-API-Key when an admin key is set', async () => {
    setAdminKey('  abc123  ')
    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    await fetchDatasets()
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['X-API-Key']).toBe('abc123')
  })

  it('prefers a bearer user session over the legacy API key', async () => {
    setAdminKey('abc123')
    setAuthSession({ access_token: 'session-token', expires_at: Math.floor(Date.now() / 1000) + 3600 })
    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    await fetchDatasets()
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers.Authorization).toBe('Bearer session-token')
    expect(init.headers['X-API-Key']).toBeUndefined()
  })

  it('drops expired bearer sessions before building request headers', async () => {
    setAdminKey('abc123')
    setAuthSession({ access_token: 'expired-token', expires_at: Math.floor(Date.now() / 1000) - 1 })
    expect(getAuthSession()).toBeNull()
    fetchMock.mockResolvedValueOnce(jsonResponse([]))

    await fetchDatasets()

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers.Authorization).toBeUndefined()
    expect(init.headers['X-API-Key']).toBe('abc123')
    expect(window.localStorage.getItem(AUTH_SESSION_STORAGE)).toBeNull()
  })

  it('loads auth configuration from the public auth endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        mode: 'supabase',
        password_login_enabled: true,
        api_key_enabled: false,
        supabase_enabled: true,
      }),
    )

    await expect(fetchAuthConfig()).resolves.toMatchObject({
      mode: 'supabase',
      supabase_enabled: true,
    })

    const [url] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/auth\/config$/)
  })

  it('stores the session from password login and clears a legacy admin key', async () => {
    setAdminKey('legacy-secret')
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        access_token: 'session-token',
        expires_at: Math.floor(Date.now() / 1000) + 3600,
        user: { authenticated: true, provider: 'local', email: 'admin@example.com', roles: ['admin'] },
      }),
    )

    const session = await loginUser({ email: 'admin@example.com', password: 's3cret' })

    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual({ email: 'admin@example.com', password: 's3cret' })
    expect(session.access_token).toBe('session-token')
    expect(getAuthSession()?.access_token).toBe('session-token')
    expect(getApiKey()).toBeFalsy()
  })

  it('clears stale credentials when current-user verification fails', async () => {
    setAdminKey('legacy-secret')
    setAuthSession({ access_token: 'stale-token', expires_at: Math.floor(Date.now() / 1000) + 3600 })
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'nope' }, { ok: false, status: 401 }))

    await expect(fetchCurrentUser()).rejects.toThrow(/Could not verify auth session/)

    expect(getAuthSession()).toBeNull()
    expect(getApiKey()).toBeFalsy()
  })

  it('logout clears credentials even when the endpoint is unavailable', async () => {
    setAdminKey('legacy-secret')
    setAuthSession({ access_token: 'session-token', expires_at: Math.floor(Date.now() / 1000) + 3600 })
    fetchMock.mockRejectedValueOnce(new Error('offline'))

    await logoutUser()

    expect(getAuthSession()).toBeNull()
    expect(getApiKey()).toBeFalsy()
  })

  it('fetches media artifacts with the bearer session before rendering them', async () => {
    const createObjectURL = vi.fn(() => 'blob:artifact-url')
    vi.stubGlobal('URL', { createObjectURL })
    setAuthSession({ access_token: 'session-token', expires_at: Math.floor(Date.now() / 1000) + 3600 })
    fetchMock.mockResolvedValueOnce(blobResponse())

    await expect(resolveMediaUrl('/media/annotated.webm')).resolves.toBe('blob:artifact-url')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/media\/annotated\.webm$/)
    expect(init.headers.Authorization).toBe('Bearer session-token')
    expect(createObjectURL).toHaveBeenCalled()
  })
})

describe('model lifecycle requests', () => {
  it('uploadModel POSTs multipart with the metadata fields', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ model_id: 'm1' }))
    const file = new File([new Uint8Array([1, 2, 3])], 'm.pt')
    const result = await uploadModel({ file, label: 'My model', role: 'detector', makeDefault: true })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/models$/)
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('label')).toBe('My model')
    expect(init.body.get('make_default')).toBe('true')
    expect(result.model_id).toBe('m1')
  })

  it('promoteModel POSTs to the promote route', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ model_id: 'm1', is_default: true }))
    await promoteModel('m1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/models\/m1\/promote$/)
    expect(init.method).toBe('POST')
  })

  it('deleteModel issues a DELETE', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(null, { status: 204 }))
    await deleteModel('m1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/models\/m1$/)
    expect(init.method).toBe('DELETE')
  })

  it('evaluateModel POSTs a JSON body', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'job1', kind: 'evaluate' }))
    await evaluateModel('m1', { datasetId: 'd1', split: 'test' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/models\/m1\/evaluate$/)
    expect(JSON.parse(init.body)).toEqual({ dataset_id: 'd1', split: 'test' })
  })

  it('surfaces a backend error detail message', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Model is the committed serving model and cannot be deleted.' }, { ok: false, status: 400 }),
    )
    await expect(deleteModel('small')).rejects.toThrow(/committed serving model/)
  })
})

describe('datasets + jobs requests', () => {
  it('commitLabels POSTs the images payload', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ dataset_id: 'd1', n_committed: 2, status: 'ready' }))
    const images = [{ image_id: 'a', boxes: [], skip: false }]
    const result = await commitLabels('d1', images)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/datasets\/d1\/commit$/)
    expect(JSON.parse(init.body)).toEqual({ images })
    expect(result.n_committed).toBe(2)
  })

  it('fetchJob GETs the job by id', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'job1', status: 'running' }))
    const job = await fetchJob('job1')
    const [url] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/jobs\/job1$/)
    expect(job.status).toBe('running')
  })

  it('cancelJob POSTs to the cancel route', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 'job1', status: 'cancelled' }))
    await cancelJob('job1')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toMatch(/\/api\/jobs\/job1\/cancel$/)
    expect(init.method).toBe('POST')
  })
})
