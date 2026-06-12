import { useMemo, useState } from 'react'
import { m, useReducedMotion } from 'motion/react'
import { ScanSearch } from 'lucide-react'
import clsx from 'clsx'
import { computeCropRect } from '../lib/cropRect'
import { statusCopy } from '../catalog/statusCatalog'

const toneFor = (status) => statusCopy[status] ?? statusCopy.occluded

// Close-up verification of the detected PAPI lights. High-resolution frames
// render the lamps far too small to verify by eye, so this reframes the image
// to the union of the detected bounding boxes (original-image pixels) using
// pure CSS percentages. Each box gets a numbered badge; a legend beneath maps
// the number to Light N / state / confidence — four adjacent lamps sit too
// close for inline labels, so the legend keeps every call readable. When no
// boxes are available it shows an explicit fallback instead of an empty panel.
export function LampCropZoom({ imageUrl, naturalWidth, naturalHeight, lamps, copy }) {
  const [imageFailed, setImageFailed] = useState(false)
  const reduceMotion = useReducedMotion()
  const crop = useMemo(
    () => computeCropRect(lamps, naturalWidth, naturalHeight),
    [lamps, naturalWidth, naturalHeight],
  )

  const hasLamps = (lamps?.length ?? 0) > 0
  const canRender = crop && imageUrl && !imageFailed

  // Text alternative for the (otherwise SVG-opaque) zoomed image region; the
  // visible legend below carries the same information for sighted users.
  const cropSummary = crop
    ? crop.boxes
        .map((box) => `${copy.live.light} ${box.id} ${copy.status?.[box.status] ?? toneFor(box.status).label}`)
        .join(', ')
    : ''

  return (
    <m.article
      className="viz-card crop-zoom-card"
      initial={reduceMotion ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
    >
      <div className="viz-heading">
        <ScanSearch size={18} />
        <div>
          <h3>{copy.live.cropTitle}</h3>
          <p>{copy.live.cropText}</p>
        </div>
      </div>

      {canRender ? (
        <>
          <div
            className="crop-zoom__viewport"
            role="img"
            aria-label={`${copy.live.cropTitle}. ${cropSummary}`}
          >
            {/* The film holds the EXACT crop aspect-ratio. The image scales by
                width while the box top/left percentages resolve against this
                element's height, so both share one scale only if the box keeps
                the crop's true proportions. Carrying the ratio here (not on the
                viewport, whose max-height clamp would skew it) keeps the boxes
                pinned to the lamps regardless of the viewport's clamped size. */}
            <div
              className="crop-zoom__film"
              style={{ aspectRatio: `${crop.width} / ${crop.height}` }}
            >
              <img
                className="crop-zoom__img"
                src={imageUrl}
                alt=""
                onError={() => setImageFailed(true)}
                style={{
                  width: `${(naturalWidth / crop.width) * 100}%`,
                  left: `${-(crop.x / crop.width) * 100}%`,
                  top: `${-(crop.y / crop.height) * 100}%`,
                }}
              />
              {crop.boxes.map((box) => (
                <div
                  key={box.id}
                  className={clsx('crop-zoom__box', `is-${box.status}`)}
                  style={{
                    left: `${(box.x / crop.width) * 100}%`,
                    top: `${(box.y / crop.height) * 100}%`,
                    width: `${(box.width / crop.width) * 100}%`,
                    height: `${(box.height / crop.height) * 100}%`,
                    '--box-color': toneFor(box.status).color,
                  }}
                >
                  <span className="crop-zoom__badge mono" aria-hidden="true">
                    {box.id}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <ul className="crop-zoom__legend">
            {crop.boxes.map((box) => {
              const tone = toneFor(box.status)
              const stateLabel = copy.status?.[box.status] ?? tone.label
              return (
                <li key={box.id} style={{ '--box-color': tone.color }}>
                  <span className="crop-zoom__legend-badge mono">{box.id}</span>
                  <span className="crop-zoom__legend-text">
                    <strong>
                      {copy.live.light} {box.id}
                    </strong>
                    <span>
                      {stateLabel} · <span className="mono tnum">{box.confidence}%</span>
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>
        </>
      ) : (
        <div className="crop-zoom__fallback" role="status">
          <ScanSearch size={26} aria-hidden="true" />
          <p>
            {imageFailed
              ? copy.live.cropImageError
              : hasLamps
                ? copy.live.cropNoBox
                : copy.live.cropNoDetection}
          </p>
        </div>
      )}
    </m.article>
  )
}
