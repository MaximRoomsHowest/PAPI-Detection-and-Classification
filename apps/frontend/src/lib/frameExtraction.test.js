/**
 * Tests for extractFrameImages — the only export of frameExtraction.js.
 *
 * Two behaviours are pinned:
 *
 *   1. Pure passthrough: a non-video file is returned as a single
 *      { file, label: file.name, timeSeconds: null } entry, with no DOM touched.
 *
 *   2. The canvas.toBlob timeout path: extractFrameImages encodes each sampled
 *      frame via an internal canvasToJpeg() that races canvas.toBlob against a
 *      15s timer. If toBlob never fires its callback (a real hazard on some
 *      codecs), the promise must REJECT with "Timed out encoding a video frame."
 *      rather than hanging forever.
 *
 * The video path is exercised by replacing document.createElement('video'|
 * 'canvas') and URL.createObjectURL/revokeObjectURL with controllable stubs:
 *   - the <video> stub dispatches loadedmetadata + seeked on a microtask (so it
 *     lands after extractFrameImages attaches its listeners), independent of the
 *     fake timer driving the encode timeout;
 *   - the <canvas> stub's getContext('2d') returns a no-op drawImage, and its
 *     toBlob is configurable (never-call vs. immediate success).
 * Microtasks are NOT faked by vitest's timers, so event delivery proceeds while
 * we fast-forward the 15s encode timeout with vi.advanceTimersByTime.
 *
 * The happy video path is covered to the extent jsdom allows (one frame, a
 * synchronous toBlob success). drawImage / real codec encoding cannot run in
 * jsdom, hence the stubbed 2d context.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'

import { extractFrameImages } from './frameExtraction.js'

const realCreateElement = document.createElement.bind(document)

// jsdom doesn't implement URL.createObjectURL / revokeObjectURL at all, so we
// can't spy them (there's nothing to replace). We install plain functions and
// remove them in afterEach. revokedUrls records what got released so a test can
// assert the cleanup ran.
const revokedUrls = []

/**
 * Install video/canvas/URL stubs. `toBlobBehavior` controls the canvas:
 *   - 'never'   : toBlob never invokes its callback (drives the timeout path)
 *   - 'success' : toBlob invokes the callback synchronously with a Blob
 *   - 'null'    : toBlob invokes the callback with null (encode produced nothing)
 * Returns a restore() to undo the createElement spy.
 */
function installMediaStubs({ width = 1280, height = 720, duration = 0.4, toBlobBehavior = 'never' } = {}) {
  URL.createObjectURL = () => 'blob:mock'
  URL.revokeObjectURL = (value) => {
    revokedUrls.push(value)
  }

  const spy = vi.spyOn(document, 'createElement').mockImplementation((tag) => {
    if (tag === 'video') {
      // Real <video> is a working EventTarget; we only override the bits the
      // code reads (dimensions, duration) and make currentTime drive `seeked`.
      const video = realCreateElement('video')
      Object.defineProperty(video, 'videoWidth', { configurable: true, get: () => width })
      Object.defineProperty(video, 'videoHeight', { configurable: true, get: () => height })
      Object.defineProperty(video, 'duration', { configurable: true, get: () => duration })
      let current = 0
      Object.defineProperty(video, 'currentTime', {
        configurable: true,
        get: () => current,
        set: (value) => {
          current = value
          // Resolve the pending seekVideo() await on a microtask.
          queueMicrotask(() => video.dispatchEvent(new Event('seeked')))
        },
      })
      // Setting .src kicks off metadata "loading"; fire loadedmetadata once the
      // caller has attached its listener (next microtask).
      Object.defineProperty(video, 'src', {
        configurable: true,
        set: () => {
          queueMicrotask(() => video.dispatchEvent(new Event('loadedmetadata')))
        },
        get: () => 'blob:mock',
      })
      return video
    }
    if (tag === 'canvas') {
      const canvas = realCreateElement('canvas')
      canvas.getContext = () => ({ drawImage: () => {} })
      canvas.toBlob = (callback) => {
        if (toBlobBehavior === 'never') return
        if (toBlobBehavior === 'null') {
          callback(null)
          return
        }
        callback(new Blob(['frame-bytes'], { type: 'image/jpeg' }))
      }
      return canvas
    }
    return realCreateElement(tag)
  })

  return () => spy.mockRestore()
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  delete URL.createObjectURL
  delete URL.revokeObjectURL
  revokedUrls.length = 0
})

describe('extractFrameImages — non-video passthrough', () => {
  it('returns a single passthrough entry for an image file (no DOM work)', async () => {
    const createSpy = vi.spyOn(document, 'createElement')
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' })

    const frames = await extractFrameImages(file)

    expect(frames).toEqual([{ file, label: 'photo.jpg', timeSeconds: null }])
    // The image branch returns before any element is created.
    expect(createSpy).not.toHaveBeenCalled()
  })

  it('treats a typeless file as a passthrough (type does not start with "video")', async () => {
    const file = new File(['x'], 'mystery', { type: '' })
    const frames = await extractFrameImages(file)
    expect(frames).toHaveLength(1)
    expect(frames[0].timeSeconds).toBeNull()
    expect(frames[0].file).toBe(file)
  })
})

describe('extractFrameImages — video happy path (stubbed canvas)', () => {
  it('returns one frame entry with a jpeg File and a numeric timeSeconds', async () => {
    const restore = installMediaStubs({ duration: 0.4, toBlobBehavior: 'success' })
    const file = new File(['x'], 'clip.mp4', { type: 'video/mp4' })

    const frames = await extractFrameImages(file)

    expect(frames).toHaveLength(1) // floor(0.4*2)=0 -> clamped to 1 sample
    expect(frames[0].label).toBe('Frame 1')
    expect(typeof frames[0].timeSeconds).toBe('number')
    expect(frames[0].file).toBeInstanceOf(File)
    expect(frames[0].file.type).toBe('image/jpeg')
    // The frame filename is derived from the source name with a -frame-NN suffix.
    expect(frames[0].file.name).toBe('clip-frame-01.jpg')
    // The object URL must be released.
    expect(revokedUrls).toContain('blob:mock')

    restore()
  })

  it('rejects when the canvas yields a null blob', async () => {
    installMediaStubs({ duration: 0.4, toBlobBehavior: 'null' })
    const file = new File(['x'], 'clip.mp4', { type: 'video/mp4' })

    await expect(extractFrameImages(file)).rejects.toThrow(/Could not extract a video frame/i)
  })
})

describe('extractFrameImages — canvas.toBlob timeout path', () => {
  it('rejects with a timeout error when toBlob never invokes its callback', async () => {
    vi.useFakeTimers()
    installMediaStubs({ duration: 0.4, toBlobBehavior: 'never' })
    const file = new File(['x'], 'clip.mp4', { type: 'video/mp4' })

    const promise = extractFrameImages(file)
    // Attach a rejection handler immediately so the eventual rejection is not
    // flagged as unhandled while we advance the clock.
    const assertion = expect(promise).rejects.toThrow(/Timed out encoding a video frame/i)

    // Let the queued microtasks (loadedmetadata, then seeked) flush so the code
    // reaches canvasToJpeg and arms the 15s timer...
    await vi.advanceTimersByTimeAsync(0)
    // ...then fast-forward past the encode timeout.
    await vi.advanceTimersByTimeAsync(15_000)

    await assertion
  })
})
