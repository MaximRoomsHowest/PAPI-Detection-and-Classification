import { useEffect } from 'react'

// Close a popover/menu when a pointerdown lands outside `ref`. Only attaches
// the listener while `active` is true, so a closed menu costs nothing.
export function useClickOutside(ref, onClose, active) {
  useEffect(() => {
    if (!active) return undefined
    const handlePointerDown = (event) => {
      if (!ref.current?.contains(event.target)) {
        onClose()
      }
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [ref, onClose, active])
}
