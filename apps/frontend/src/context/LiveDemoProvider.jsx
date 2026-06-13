import { useCallback, useMemo, useRef, useState } from 'react'
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

  // Video seek channel: the transition list (ResultPanel) and the stage's
  // <video> live in sibling components, so "click a transition, jump the
  // video there" flows through context. The nonce makes re-clicking the same
  // transition seek again; videoDurationS doubles as the honest "a video is
  // actually mounted" gate for showing the jump buttons at all.
  const [videoSeek, setVideoSeek] = useState(null)
  const [videoDurationS, setVideoDurationS] = useState(null)
  const seekNonce = useRef(0)
  const requestFrameSeek = useCallback((frame) => {
    seekNonce.current += 1
    setVideoSeek({ frame, nonce: seekNonce.current })
  }, [])
  const reportVideoDuration = useCallback((duration) => {
    setVideoDurationS(Number.isFinite(duration) && duration > 0 ? duration : null)
  }, [])

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
    () => ({
      ...analysis,
      activeScenario,
      activeState,
      videoSeek,
      videoDurationS,
      requestFrameSeek,
      reportVideoDuration,
    }),
    [
      analysis,
      activeScenario,
      activeState,
      videoSeek,
      videoDurationS,
      requestFrameSeek,
      reportVideoDuration,
    ],
  )

  return <LiveDemoContext.Provider value={value}>{children}</LiveDemoContext.Provider>
}
