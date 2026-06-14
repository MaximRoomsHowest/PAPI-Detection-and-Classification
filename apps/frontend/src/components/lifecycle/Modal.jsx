import { useRef } from 'react'
import { X } from 'lucide-react'
import { useModalA11y } from '../../hooks/useModalA11y'

// Minimal accessible modal (focus trap + Escape + scroll lock via useModalA11y),
// reused by the model-upload, evaluate, and assisted-labeling-review surfaces.
export function Modal({ open, onClose, title, children, closeLabel = 'Close', wide = false }) {
  const ref = useRef(null)
  useModalA11y(ref, open, onClose)
  if (!open) return null
  return (
    <div className="lc-modal-backdrop">
      {/* Full-area dismiss control: a real <button> so click-to-close is keyboard-
          and screen-reader-accessible (Escape is also handled by useModalA11y). */}
      <button type="button" className="lc-modal__scrim" aria-label={closeLabel} onClick={onClose} />
      <div
        className={`lc-modal${wide ? ' lc-modal--wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
      >
        <div className="lc-modal__head">
          <h2 className="lc-modal__title">{title}</h2>
          <button className="icon-button" type="button" onClick={onClose} aria-label={closeLabel}>
            <X size={18} />
          </button>
        </div>
        <div className="lc-modal__body">{children}</div>
      </div>
    </div>
  )
}
