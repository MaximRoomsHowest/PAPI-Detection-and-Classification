// Single source for the OS "reduce motion" accessibility preference. SSR-safe and tolerant of
// jsdom/older browsers that lack matchMedia. Used by the glide-slope simulator and the
// frame-stage scroll so the check can't drift between them.
export function prefersReducedMotion() {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}
