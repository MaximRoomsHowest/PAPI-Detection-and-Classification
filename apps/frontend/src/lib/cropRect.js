// Pure geometry for the PAPI crop/zoom verification view.
//
// The backend returns each lamp's bbox in the ORIGINAL image's pixel space
// (ultralytics maps detections back to the source resolution), so every value
// here is in original pixels. The component turns these into CSS percentages
// at render time with a single scale factor, which keeps the zoom fully
// responsive without any canvas or runtime measurement.

const DEFAULT_PAD_RATIO = 0.35
const MIN_PAD_PX = 24
// Floor on the crop size so a cluster of tiny, distant PAPI detections (often only
// a few pixels each) isn't zoomed ~10-15x into a blurry sliver that excludes the
// lamp glow and the surrounding scene. Framing at least this much keeps the lamps
// legible and in context; on a real high-resolution drone frame the crop still
// frames in tight (the ratio dominates the absolute floor there).
const MIN_CROP_PX = 200
const MIN_CROP_RATIO = 0.15

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

// Expand a 1-D [start, size] span to at least `min` (never exceeding `total`),
// keeping it centred on its original midpoint and inside [0, total].
function expandSpan(start, size, min, total) {
  const target = Math.min(total, Math.max(size, min))
  if (target === size) {
    return [start, size]
  }
  const center = start + size / 2
  return [clamp(center - target / 2, 0, total - target), target]
}

/**
 * Compute a padded crop rectangle that frames every detected lamp, plus the
 * per-lamp boxes expressed relative to the crop origin.
 *
 * @param {Array<{id?, index?, status?, state?, confidence?, bbox?: {x1,y1,x2,y2}}>} lamps
 * @param {number} naturalWidth  original image width in px
 * @param {number} naturalHeight original image height in px
 * @param {{ padRatio?: number }} [options]
 * @returns {null | { x, y, width, height, boxes: Array<{id, status, confidence, x, y, width, height}> }}
 *   Returns null when nothing is drawable (no image size, or no lamp has a bbox).
 */
export function computeCropRect(lamps, naturalWidth, naturalHeight, options = {}) {
  if (!naturalWidth || !naturalHeight) {
    return null
  }

  const boxes = (lamps ?? [])
    .filter((lamp) => lamp && lamp.bbox && Number.isFinite(lamp.bbox.x1))
    .map((lamp) => ({
      id: lamp.id ?? lamp.index,
      status: lamp.status ?? lamp.state,
      confidence: lamp.confidence,
      x1: lamp.bbox.x1,
      y1: lamp.bbox.y1,
      x2: lamp.bbox.x2,
      y2: lamp.bbox.y2,
    }))

  if (!boxes.length) {
    return null
  }

  const unionX1 = Math.min(...boxes.map((box) => box.x1))
  const unionY1 = Math.min(...boxes.map((box) => box.y1))
  const unionX2 = Math.max(...boxes.map((box) => box.x2))
  const unionY2 = Math.max(...boxes.map((box) => box.y2))

  const padRatio = options.padRatio ?? DEFAULT_PAD_RATIO
  const padX = Math.max(MIN_PAD_PX, (unionX2 - unionX1) * padRatio)
  const padY = Math.max(MIN_PAD_PX, (unionY2 - unionY1) * padRatio)

  let x = clamp(unionX1 - padX, 0, naturalWidth)
  let y = clamp(unionY1 - padY, 0, naturalHeight)
  let width = clamp(unionX2 + padX, x, naturalWidth) - x
  let height = clamp(unionY2 + padY, y, naturalHeight) - y

  // Bound the zoom: expand a too-tight crop (tiny detections) to a sensible
  // minimum so the lamps render in context instead of an over-zoomed blur.
  const minW = Math.max(MIN_CROP_PX, naturalWidth * MIN_CROP_RATIO)
  const minH = Math.max(MIN_CROP_PX * 0.66, naturalHeight * MIN_CROP_RATIO)
  ;[x, width] = expandSpan(x, width, minW, naturalWidth)
  ;[y, height] = expandSpan(y, height, minH, naturalHeight)

  return {
    x,
    y,
    width,
    height,
    boxes: boxes.map((box) => ({
      id: box.id,
      status: box.status,
      confidence: box.confidence,
      // Relative to the crop origin, still in original-pixel units. The
      // component divides by crop width/height to get CSS percentages.
      x: box.x1 - x,
      y: box.y1 - y,
      width: box.x2 - box.x1,
      height: box.y2 - box.y1,
    })),
  }
}
