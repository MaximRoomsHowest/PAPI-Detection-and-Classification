import { Radar } from 'lucide-react'
import clsx from 'clsx'
import { LampCard } from '../LampCard'
import { InlineMetric } from '../InlineMetric'
import { formatDistanceM, formatDurationMs } from '../../lib/format'
import { useLiveDemo } from '../../context/liveDemoContext'

// The analysis result aside: state summary, per-lamp cards, the detection/latency
// metrics, the PAPI elevation-angle readout (with provenance + plausibility), and
// any red<->white transitions. Falls back to the empty prompt until a backend
// analysis has produced a result. Reads the active scenario/state from context.
export function ResultPanel({ copy }) {
  const { activeScenario, activeState, runways, selectedRunwayId, backendScenario } = useLiveDemo()

  // The Live Demo shows real backend output only. Until an analysis has run the
  // result panel stays empty rather than displaying a canned "demo" preset.
  const hasResult = Boolean(backendScenario)

  // The runway the *displayed* result was scored against — the backend echoes
  // runway_id on the payload, so this reflects what was actually analysed (not a
  // selector change made afterwards), mapped to its label.
  const usedRunwayId = activeScenario?.rawResult?.runway_id ?? selectedRunwayId
  const usedRunwayLabel =
    runways.find((runway) => runway.id === usedRunwayId)?.label ?? usedRunwayId

  return (
    <aside className="analysis-panel" id="analysis-details">
      {hasResult ? (
        <>
          <div className="state-summary">
            <span className="status-dot" style={{ '--dot-color': activeState.color }} />
            <div>
              <p>{activeScenario.summary}</p>
              <h3>{activeState.label}</h3>
              <small>{activeState.description}</small>
              {/* On an "unknown" verdict, show how many of the 4 lamps were
                  actually detected so the result reads as "found 3, one was
                  too faint" rather than a total miss (the yolo26s model is
                  precise but conservative on dim/distant lamps). */}
              {activeScenario.stateId === 'unknown' && (
                <small className="state-summary__count">
                  {copy.live.lampsDetected
                    .replace(
                      '{n}',
                      activeScenario.lamps.filter(
                        (lamp) => lamp.status === 'red' || lamp.status === 'white',
                      ).length,
                    )
                    .replace('{total}', activeScenario.lamps.length)}
                </small>
              )}
            </div>
          </div>

          <div className="lamp-list">
            {activeScenario.lamps.map((lamp) => (
              <LampCard key={lamp.id} lamp={lamp} copy={copy} />
            ))}
          </div>

          {/* Real backend metrics only — detection confidence + processing time. */}
          <div className="metric-grid metric-grid--compact">
            <InlineMetric
              label={copy.live.detection}
              value={activeScenario.metrics.boxConfidence}
              suffix="%"
            />
            <InlineMetric
              label={copy.live.latency}
              value={formatDurationMs(activeScenario.metrics.latency).value}
              suffix={formatDurationMs(activeScenario.metrics.latency).suffix}
            />
          </div>

          {/* PAPI elevation angle — real WGS-84 geometry from the drone GPS /
              manual telemetry vs the runway's surveyed lamps. "Unavailable"
              when no drone position was supplied or read from EXIF. */}
          <div
            className={clsx(
              'angle-readout',
              !activeScenario.angleSummary?.available && 'unavailable',
              activeScenario.angleSummary?.available &&
                activeScenario.angleSummary?.plausible === false &&
                'implausible',
            )}
          >
            <span>{copy.live.elevationAngle}</span>
            {activeScenario.angleSummary?.available ? (
              <>
                <strong className="tnum">
                  {activeScenario.angleSummary.value}
                  <small>°</small>
                  {/* RTK 1-sigma band — only present when the file carried DJI
                      RTK std, so it never fabricates a confidence figure. */}
                  {activeScenario.angleSummary.uncertainty != null && (
                    <small className="angle-readout__band">
                      ± {activeScenario.angleSummary.uncertainty}° {copy.live.angleUncertainty}
                    </small>
                  )}
                </strong>
                {/* Provenance of the position, localized in translateScenario:
                    "from your input" / "from image GPS" / "from telemetry file". */}
                <p>{activeScenario.angleSummary.source}</p>
                {/* Which runway the angle was scored against + how far the drone
                    was from it — the runway<->metadata relationship, made explicit. */}
                <p className="angle-readout__context">
                  {copy.live.runwayUsed.replace('{runway}', usedRunwayLabel)}
                  {activeScenario.angleSummary.nearestLampDistanceM != null &&
                    ` · ${copy.live.nearestLampDistance.replace(
                      '{distance}',
                      formatDistanceM(activeScenario.angleSummary.nearestLampDistanceM),
                    )}`}
                </p>
                {activeScenario.angleSummary.plausible === false && (
                  <p className="angle-readout__warning" role="alert">
                    {copy.live.angleImplausible}
                  </p>
                )}
              </>
            ) : (
              <>
                <strong>{copy.live.angleUnavailable}</strong>
                <p>{copy.live.angleHint}</p>
              </>
            )}
          </div>

          {activeScenario.transitions?.length > 0 && (
            <div className="transition-readout">
              <span>{copy.live.transitionsHeading}</span>
              {/* Which method produced these transitions — the backend echoes it, so if "model"
                  was requested but no 3-class model was available this reads "Tracking" (the
                  graceful fallback), telling the user exactly what they are looking at. */}
              {activeScenario.rawResult?.transition_method && (
                <small className="transition-readout__method">
                  {copy.live.transitionMethodUsed.replace(
                    '{method}',
                    activeScenario.rawResult.transition_method === 'model'
                      ? copy.live.transitionMethodModel
                      : copy.live.transitionMethodTracking,
                  )}
                </small>
              )}
              <ul>
                {activeScenario.transitions.map((event, index) => (
                  <li key={`${event.lamp_index}-${event.frame_index}-${index}`}>
                    {`${copy.live.light} ${event.lamp_index}: `}
                    {`${copy.status?.[event.from_state] ?? event.from_state} → ${copy.status?.[event.to_state] ?? event.to_state}`}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <div className="analysis-empty">
          <Radar size={28} />
          <p>{copy.live.emptyState}</p>
        </div>
      )}
    </aside>
  )
}
