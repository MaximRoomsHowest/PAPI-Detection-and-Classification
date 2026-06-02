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
    // Capture phase: fire before any element-level pointerdown handler that might
    // call stopPropagation(), so an outside click always closes the menu even if
    // a parent in the tree swallows the bubbling event. The contains() check
    // keeps clicks inside `ref` from closing it, so behavior is otherwise identical.
    document.addEventListener('pointerdown', handlePointerDown, true)
    return () => document.removeEventListener('pointerdown', handlePointerDown, true)
  }, [ref, onClose, active])
}
