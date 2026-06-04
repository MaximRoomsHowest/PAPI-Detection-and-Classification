import clsx from 'clsx'
import { stateCatalog } from '../catalog/stateCatalog'
import { translateState } from '../i18n/translate'

// Tally the per-lamp states of one scenario into white / red / transition /
// other counts. `obscured` and `occluded` (non-detections) fold into `other`
// so the header counters only foreground the two states a controller reads.
function countLampStates(lamps) {
  return lamps.reduce(
    (counts, lamp) => {
      const state = lamp.status ?? lamp.state
      if (state === 'white') counts.white += 1
      else if (state === 'red') counts.red += 1
      else if (state === 'transition') counts.transition += 1
      else counts.other += 1
      return counts
    },
    { white: 0, red: 0, transition: 0, other: 0 },
  )
}

// Compact "2 white + 2 red" style summary for a frame row, built from the
// translated status labels so it stays localized in every locale.
function formatLampCounts(lamps, copy) {
  const counts = countLampStates(lamps)
  const parts = []
  if (counts.white) parts.push(`${counts.white} ${copy.status.white.toLowerCase()}`)
  if (counts.red) parts.push(`${counts.red} ${copy.status.red.toLowerCase()}`)
  if (counts.transition) parts.push(`${counts.transition} ${copy.status.transition.toLowerCase()}`)
  if (counts.other) parts.push(`${counts.other} ${copy.status.occluded.toLowerCase()}`)
  return parts.length ? parts.join(' + ') : copy.status.occluded
}

function frameAngle(scenario, copy) {
  return scenario.angleSummary?.available
    ? `${scenario.angleSummary.value}°`
    : copy.live.angleUnavailable
}

// Scrollable list of every analyzed frame for an image upload: each row shows
// the frame label, its lamp pattern, PAPI state, elevation angle, and detection
// confidence, and clicking it jumps the whole result panel to that frame. Only
// rendered for multi-image uploads — folders/videos collapse to one aggregated
// result with no per-frame stepping.
export function AnalysisHistoryPanel({ activeScenario, backendFrames, backendFrameIndex, onSelectFrame, copy }) {
  const history = backendFrames.length ? backendFrames : []
  const selected = history[backendFrameIndex] ?? activeScenario
  const lampCounts = countLampStates(selected?.lamps ?? [])
  const selectedAngle = frameAngle(selected, copy)

  return (
    <section className="history-panel" id="analysis-history" aria-label={copy.live.frameHistory}>
      <div className="history-heading">
        <div>
          <h3>{copy.live.historyTitle}</h3>
          <p>{copy.live.historySubtitle}</p>
        </div>
        <span>
          {history.length
            ? `${history.length} ${copy.live.analyzedFrames.toLowerCase()}`
            : copy.live.historyEmpty}
        </span>
      </div>

      <div className="history-stat-grid">
        <div className="history-stat">
          <span>{copy.live.selectedFrame}</span>
          <strong>{selected?.frame}</strong>
        </div>
        <div className="history-stat history-stat--white">
          <span>{copy.status.white}</span>
          <strong>{lampCounts.white}</strong>
        </div>
        <div className="history-stat history-stat--red">
          <span>{copy.status.red}</span>
          <strong>{lampCounts.red}</strong>
        </div>
        <div className="history-stat">
          <span>{copy.live.angle}</span>
          <strong>{selectedAngle}</strong>
        </div>
      </div>

      {history.length > 0 && (
        <div className="history-list" role="list" aria-label={copy.live.frameHistory}>
          {history.map((frame, index) => {
            const state = translateState(
              stateCatalog.find((item) => item.id === frame.stateId) ?? stateCatalog[stateCatalog.length - 1],
              copy,
            )

            return (
              <div className="history-row-item" role="listitem" key={frame.logId ?? frame.frame}>
                <button
                  className={clsx('history-row', index === backendFrameIndex && 'active')}
                  type="button"
                  aria-current={index === backendFrameIndex}
                  onClick={() => onSelectFrame(index)}
                >
                  <span className="history-frame">{frame.frame}</span>
                  <span className="history-pattern">{formatLampCounts(frame.lamps, copy)}</span>
                  <span className="history-state">{state.label}</span>
                  <span className="history-angle">{frameAngle(frame, copy)}</span>
                  <span className="history-confidence">{frame.metrics?.boxConfidence ?? '—'}%</span>
                </button>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
