import clsx from 'clsx'
import { statusCopy } from '../catalog/statusCatalog'

export function LampCard({ lamp, copy }) {
  // Fall back to the "occluded" tone for any unexpected backend state so a new
  // lamp status can never crash the card (mirrors the guard in LampCropZoom).
  const status = statusCopy[lamp.status] ?? statusCopy.occluded
  const label = copy.status[lamp.status] ?? status.label
  // Flag a shaky verdict — a real detection under 50% confidence — with a
  // language-neutral ⚠ cue and amber styling rather than showing it as certain.
  const isLowConfidence = status.tone !== 'occluded' && Number(lamp.confidence) < 50

  return (
    <div
      className={clsx(
        'lamp-card',
        `lamp-${status.tone}`,
        isLowConfidence && !lamp.inferred && 'is-low-confidence',
        lamp.inferred && 'is-inferred',
      )}
    >
      <div className="lamp-preview">
        <span />
        <strong>
          {copy.live.light} {lamp.id}
        </strong>
      </div>
      <div>
        <p>{label}</p>
        <small>
          {/* Low-confidence flag carried by real localized text (not colour or the
              decorative ⚠ alone) so screen-reader users hear "Low confidence" too,
              not just the percentage — WCAG 1.4.1 / information parity. */}
          {isLowConfidence && !lamp.inferred && (
            <span className="lamp-card__warn">
              <span aria-hidden="true">⚠ </span>
              {copy.live.lowConfidence}
              {' · '}
            </span>
          )}
          {lamp.inferred ? copy.live.inferredFromAngle : `${lamp.confidence}% ${copy.live.confidenceLabel}`}
        </small>
      </div>
    </div>
  )
}
