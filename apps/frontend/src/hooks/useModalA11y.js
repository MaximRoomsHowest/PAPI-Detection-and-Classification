import { useEffect } from 'react'

// Modal a11y/UX (audit IMP-FE-11): close on Escape, move focus into the dialog
// on open, trap Tab focus inside it, lock background scroll, and restore focus
// to the trigger on close. `ref` points at the dialog element; `isOpen` gates
// the whole effect; `onClose` is called on Escape.
export function useModalA11y(ref, isOpen, onClose) {
  useEffect(() => {
    if (!isOpen) return undefined
    const previouslyFocused = document.activeElement
    const focusableSelector =
      'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      // Trap focus inside the dialog (WCAG 2.4.3) so Tab can't reach the page behind it.
      if (event.key !== 'Tab') return
      const focusable = ref.current?.querySelectorAll(focusableSelector)
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    // Lock background scroll while the dialog is open, restoring it on close.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ref.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus()
    }
  }, [ref, isOpen, onClose])
}
