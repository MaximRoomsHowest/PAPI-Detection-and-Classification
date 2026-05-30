import clsx from 'clsx'
import { statusCopy } from '../catalog/statusCatalog'

export function LampCard({ lamp, copy }) {
  const status = statusCopy[lamp.status]
  const label = copy.status[lamp.status] ?? status.label

  return (
    <div className={clsx('lamp-card', `lamp-${status.tone}`)}>
      <div className="lamp-preview">
        <span />
        <strong>
          {copy.live.light} {lamp.id}
        </strong>
      </div>
      <div>
        <p>{label}</p>
        <small>
          {lamp.confidence}% {copy.live.confidenceLabel}
        </small>
      </div>
    </div>
  )
}
