import clsx from 'clsx'
import { statusCopy } from '../catalog/statusCatalog'

export function LampCard({ lamp, copy }) {
  const status = statusCopy[lamp.status]
  const label = copy.status[lamp.status] ?? status.label
  // Flag a shaky verdict — a real detection under 50% confidence — with a
  // language-neutral ⚠ cue and amber styling rather than showing it as certain.
  const isLowConfidence = status.tone !== 'occluded' && Number(lamp.confidence) < 50

  return (
    <div className={clsx('lamp-card', `lamp-${status.tone}`, isLowConfidence && 'is-low-confidence')}>
      <div className="lamp-preview">
        <span />
        <strong>
          {copy.live.light} {lamp.id}
        </strong>
      </div>
      <div>
        <p>{label}</p>
        <small>
          {isLowConfidence && <span aria-hidden="true">⚠ </span>}
          {lamp.confidence}% {copy.live.confidenceLabel}
        </small>
      </div>
    </div>
  )
}
