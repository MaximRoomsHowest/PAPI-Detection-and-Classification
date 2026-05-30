import clsx from 'clsx'
import { statusCopy } from '../catalog/statusCatalog'

export function LampCard({ lamp, copy }) {
  const status = statusCopy[lamp.status]
  const label = copy.status[lamp.status] ?? status.label

  return (
    <div className={clsx('lamp-card', `lamp-${status.tone}`)}>
      <div className="lamp-preview">
        <span />
        <strong>Lamp {lamp.id}</strong>
      </div>
      <div>
        <p>{label}</p>
        <small>{lamp.confidence}% confidence</small>
      </div>
      <div className="transition-meter" aria-label={`${lamp.transition}% transition score`}>
        <span style={{ width: `${lamp.transition}%` }} />
      </div>
    </div>
  )
}
