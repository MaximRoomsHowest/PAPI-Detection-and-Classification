import { useMemo } from 'react'
import { scenarios } from '../catalog/scenarios'
import { stateCatalog } from '../catalog/stateCatalog'
import { translateScenario, translateState } from '../i18n/translate'
import { useAnalysis } from '../hooks/useAnalysis'
import { LiveDemoContext } from './liveDemoContext'

// Owns the Live-Demo state: useAnalysis() plus the derived display objects
// (activeScenario / activeState), spread into one context value so consumers
// keep the exact field names they always had. Living here — not in App — means
// a progress tick during a long analysis re-renders this provider and its
// consumers only; the shell around it (Topbar, footer, Toaster, the route
// elements themselves) keeps its `children` identity and React bails out of
// re-rendering it. Component-only export keeps Fast Refresh / react-refresh
// happy (the Context + hook live in the sibling hook-only module
// liveDemoContext.js).
export function LiveDemoProvider({ copy, children }) {
  const analysis = useAnalysis(copy)

  const activeScenarioRaw = useMemo(
    () => {
      if (analysis.activeId === 'backend' && analysis.backendScenario) {
        return analysis.backendScenario
      }
      return scenarios.find((scenario) => scenario.id === analysis.activeId) ?? scenarios[0]
    },
    [analysis.activeId, analysis.backendScenario],
  )

  const activeScenario = useMemo(
    () => translateScenario(activeScenarioRaw, copy),
    [activeScenarioRaw, copy],
  )

  const activeState = useMemo(
    () =>
      translateState(
        stateCatalog.find((state) => state.id === activeScenario.stateId) ?? stateCatalog[stateCatalog.length - 1],
        copy,
      ),
    [activeScenario, copy],
  )

  const value = useMemo(
    () => ({ ...analysis, activeScenario, activeState }),
    [analysis, activeScenario, activeState],
  )

  return <LiveDemoContext.Provider value={value}>{children}</LiveDemoContext.Provider>
}
