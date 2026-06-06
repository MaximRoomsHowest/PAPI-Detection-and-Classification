function waitFor(target, eventName) {
  return new Promise((resolve, reject) => {
    const handleEvent = () => {
      cleanup()
      resolve()
    }
    const handleError = () => {
      cleanup()
      reject(new Error(`Could not read uploaded ${target.tagName.toLowerCase()}.`))
    }
    const cleanup = () => {
      target.removeEventListener(eventName, handleEvent)
      target.removeEventListener('error', handleError)
    }

    target.addEventListener(eventName, handleEvent, { once: true })
    target.addEventListener('error', handleError, { once: true })
  })
}

// A seek can hang if the browser/codec never fires `seeked` (the same failure mode the
// canvasToJpeg timeout guards). Race the event against a timer so a stuck seek rejects
// cleanly and the caller's `finally` revokes the object URL instead of hanging forever.
const SEEK_TIMEOUT_MS = 15_000

function seekVideo(video, timeSeconds, timeoutMs = SEEK_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let settled = false
    const cleanup = () => {
      clearTimeout(timer)
      video.removeEventListener('seeked', onSeeked)
      video.removeEventListener('error', onError)
    }
    const finish = (fn) => (value) => {
      if (settled) return
      settled = true
      cleanup()
      fn(value)
    }
    const onSeeked = finish(() => resolve())
    const onError = finish(() => reject(new Error('Could not read uploaded video.')))
    const timer = setTimeout(
      finish(() => reject(new Error('Timed out seeking a video frame.'))),
      timeoutMs,
    )
    video.addEventListener('seeked', onSeeked, { once: true })
    video.addEventListener('error', onError, { once: true })
    video.currentTime = timeSeconds
  })
}

// canvas.toBlob is async with no built-in timeout; on some browsers/codecs the
// callback can simply never fire. Race it against a timer so a hung encode
// rejects cleanly instead of blocking extractFrameImages (and its caller) forever.
const CANVAS_TO_BLOB_TIMEOUT_MS = 15_000

function canvasToJpeg(canvas, fileName, timeoutMs = CANVAS_TO_BLOB_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      reject(new Error('Timed out encoding a video frame.'))
    }, timeoutMs)

    const finish = (fn) => (value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      fn(value)
    }
    const succeed = finish(resolve)
    const fail = finish(reject)

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          fail(new Error('Could not extract a video frame.'))
          return
        }
        succeed(new File([blob], fileName, { type: 'image/jpeg' }))
      },
      'image/jpeg',
      0.92,
    )
  })
}

export async function extractFrameImages(file, maxFrames = 7) {
  if (!file.type.startsWith('video')) {
    return [{ file, label: file.name, timeSeconds: null }]
  }

  const url = URL.createObjectURL(file)
  const video = document.createElement('video')
  video.src = url
  video.muted = true
  video.playsInline = true
  video.preload = 'metadata'

  try {
    await waitFor(video, 'loadedmetadata')
    const width = video.videoWidth
    const height = video.videoHeight
    if (!width || !height) {
      throw new Error('Uploaded video does not expose readable frame dimensions.')
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) {
      throw new Error('Browser canvas is not available for frame extraction.')
    }

    const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 1
    const sampleCount = Math.max(1, Math.min(maxFrames, Math.floor(duration * 2) || 1))
    const frames = []

    for (let index = 0; index < sampleCount; index += 1) {
      const ratio = sampleCount === 1 ? 0.5 : (index + 0.5) / sampleCount
      const timeSeconds = Math.min(Math.max(duration * ratio, 0), Math.max(duration - 0.05, 0))
      await seekVideo(video, timeSeconds)
      context.drawImage(video, 0, 0, width, height)
      const frameFile = await canvasToJpeg(
        canvas,
        `${file.name.replace(/\.[^.]+$/, '')}-frame-${String(index + 1).padStart(2, '0')}.jpg`,
      )
      frames.push({ file: frameFile, label: `Frame ${index + 1}`, timeSeconds })
    }

    return frames
  } finally {
    URL.revokeObjectURL(url)
  }
}

