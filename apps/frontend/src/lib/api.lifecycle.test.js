/**
 * Tests for the model-lifecycle API client (upload / promote / evaluate /
 * datasets / jobs) and the runtime admin-key plumbing. Mirrors api.test.js:
 * stub global fetch, assert URL + method + headers + body the browser sends.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ADMIN_KEY_STORAGE,
  cancelJob,
  commitLabels,
  deleteModel,
  evaluateModel,
  fetchDatasets,
  fetchJob,
  getApiKey,
  promoteModel,
  setAdminKey,
  uploadModel,
} from './api.js'

function jsonResponse(body, { ok = true, status = ok ? 200 : 500, statusText = 'OK' } = {}) {
  return { ok, status, statusText, json: async () => body }
}

let fetchMock

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(jsonResponse({}))
  vi.stubGlobal('fetch', fetchMock)
  window.localStorage.removeItem(ADMIN_KEY_STORAGE)
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.removeItem(ADMIN_KEY_STORAGE)
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
    setAdminKey('abc123')
    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    await fetchDatasets()
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['X-API-Key']).toBe('abc123')
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
