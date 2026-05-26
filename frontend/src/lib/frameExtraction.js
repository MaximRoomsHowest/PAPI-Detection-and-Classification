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

async function seekVideo(video, timeSeconds) {
  const seeked = waitFor(video, 'seeked')
  video.currentTime = timeSeconds
  await seeked
}

function canvasToJpeg(canvas, fileName) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          reject(new Error('Could not extract a video frame.'))
          return
        }
        resolve(new File([blob], fileName, { type: 'image/jpeg' }))
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

