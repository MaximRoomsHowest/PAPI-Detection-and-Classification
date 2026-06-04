const DEFAULT_FPS = 3
const DEFAULT_MIME_TYPES = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm']

function waitForImage(image) {
  return new Promise((resolve, reject) => {
    image.onload = () => resolve()
    image.onerror = () => reject(new Error('Could not load one of the folder images for video export.'))
  })
}

async function loadImage(url) {
  const image = new Image()
  image.decoding = 'async'
  image.src = url
  await waitForImage(image)
  return image
}

function supportedMimeType() {
  return DEFAULT_MIME_TYPES.find((mimeType) => window.MediaRecorder?.isTypeSupported?.(mimeType)) ?? ''
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function sourceToUrl(source, createdUrls) {
  if (source.url) {
    return source.url
  }
  if (source.file) {
    const url = URL.createObjectURL(source.file)
    createdUrls.push(url)
    return url
  }
  throw new Error('Folder video source is missing a file or URL.')
}

export async function createFolderVideo(sources, { fps = DEFAULT_FPS } = {}) {
  const orderedSources = (sources ?? []).filter(Boolean)
  if (orderedSources.length < 2) {
    throw new Error('Select at least two folder images to transform them into a video.')
  }
  if (!HTMLCanvasElement.prototype.captureStream || !window.MediaRecorder) {
    throw new Error('This browser cannot record a video from folder images.')
  }

  const createdSourceUrls = []
  const chunks = []

  try {
    const firstUrl = await sourceToUrl(orderedSources[0], createdSourceUrls)
    const firstImage = await loadImage(firstUrl)
    const width = firstImage.naturalWidth || firstImage.width
    const height = firstImage.naturalHeight || firstImage.height

    if (!width || !height) {
      throw new Error('Folder images do not expose readable dimensions.')
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')

    if (!context) {
      throw new Error('Browser canvas is not available for folder video export.')
    }

    const stream = canvas.captureStream(fps)
    const mimeType = supportedMimeType()
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)

    const finished = new Promise((resolve, reject) => {
      recorder.ondataavailable = (event) => {
        if (event.data?.size) {
          chunks.push(event.data)
        }
      }
      recorder.onerror = () => reject(new Error('Could not encode the folder video.'))
      recorder.onstop = resolve
    })

    const frameDurationMs = Math.round(1000 / fps)
    recorder.start()

    for (const [index, source] of orderedSources.entries()) {
      const url = index === 0 ? firstUrl : await sourceToUrl(source, createdSourceUrls)
      const image = index === 0 ? firstImage : await loadImage(url)
      context.fillStyle = '#000000'
      context.fillRect(0, 0, width, height)
      context.drawImage(image, 0, 0, width, height)
      await delay(frameDurationMs)
    }

    recorder.stop()
    await finished
    stream.getTracks().forEach((track) => track.stop())

    const blob = new Blob(chunks, { type: mimeType || 'video/webm' })
    return {
      url: URL.createObjectURL(blob),
      blob,
      mimeType: blob.type,
      frameCount: orderedSources.length,
      fps,
    }
  } finally {
    createdSourceUrls.forEach((url) => URL.revokeObjectURL(url))
  }
}
