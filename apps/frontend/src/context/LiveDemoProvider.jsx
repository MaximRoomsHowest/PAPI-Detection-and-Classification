import { LiveDemoContext } from './liveDemoContext'

// Thin provider for the Live-Demo subtree. The actual value (useAnalysis() spread
// with the App-derived activeScenario / activeState) is assembled in App.jsx and
// passed in, so this component stays a pure pass-through. Component-only export
// keeps Fast Refresh / react-refresh happy (the Context + hook live in the
// sibling hook-only module liveDemoContext.js).
export function LiveDemoProvider({ value, children }) {
  return <LiveDemoContext.Provider value={value}>{children}</LiveDemoContext.Provider>
}
