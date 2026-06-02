import { createContext, useContext } from 'react'

// Live-Demo shared-state context internals (the Context object + the consumer
// hook). Kept in a hook-only module — separate from the JSX provider component —
// so eslint-plugin-react-refresh (only-export-components) stays happy: a file
// must not export a component alongside non-component values.
//
// The context value's shape is exactly useAnalysis()'s return object spread
// alongside { activeScenario, activeState } (see App.jsx). No field is renamed,
// so the data the Live Demo page reads is identical to the old drilled props.
export const LiveDemoContext = createContext(null)

// Consumer hook. Throws if used outside a provider so a misuse surfaces as a
// clear error in development instead of a confusing "cannot read property of
// null" deep in the render.
export function useLiveDemo() {
  const value = useContext(LiveDemoContext)
  if (value === null) {
    throw new Error('useLiveDemo must be used within a <LiveDemoProvider>')
  }
  return value
}
