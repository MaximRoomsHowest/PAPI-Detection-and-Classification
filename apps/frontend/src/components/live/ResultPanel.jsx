import { Play, Radar } from 'lucide-react'
import clsx from 'clsx'
import { LampCard } from '../LampCard'
import { InlineMetric } from '../InlineMetric'
import { formatDistanceM, formatDurationMs } from '../../lib/format'
import { useLiveDemo } from '../../context/liveDemoContext'

function formatVideoTime(seconds) {
  const whole = Math.max(0, Math.floor(seconds))
  const minutes = String(Math.floor(whole / 60)).padStart(2, '0')
  return `${minutes}:${String(whole % 60).padStart(2, '0')}`
}

// The analysis result aside: state summary, per-lamp cards, the detection/latency
// metrics, the PAPI elevation-angle readout (with provenance + plausibility), and
// any red<->white transitions. Falls back to the empty prompt until a backend
// analysis has produced a result. Reads the active scenario/state from context.
export function ResultPanel({ copy }) {
  const {
    activeScenario,
    activeState,
    runways,
    selectedRunwayId,
    backendScenario,
    isAnalyzing,
    requestFrameSeek,
    videoDurationS,
  } = useLiveDemo()

  // Transition timestamps are clickable only while a measurable <video> is on
  // the stage; the frame->seconds mapping mirrors the stage's own seek math
  // (sampled frame index over total sampled frames, scaled to duration).
  const seekFrameCount =
    activeScenario?.perFrame?.length || activeScenario?.rawResult?.angle_track?.length || 0
  const canSeekVideo = Boolean(videoDurationS) && seekFrameCount > 1
  const frameToSeconds = (frame) =>
    (Math.min(Math.max(frame, 0), seekFrameCount - 1) / seekFrameCount) * videoDurationS

  // The Live Demo shows real backend output only. Until an analysis has run the
  // result panel stays empty rather than displaying a canned "demo" preset.
  const hasResult = Boolean(backendScenario)

  // The runway the *displayed* result was scored against — the backend echoes
  // runway_id on the payload, so this reflects what was actually analysed (not a
  // selector change made afterwards), mapped to its label.
  const usedRunwayId = activeScenario?.rawResult?.runway_id ?? selectedRunwayId
  const usedRunwayLabel =
    runways.find((runway) => runway.id === usedRunwayId)?.label ?? usedRunwayId

  // The angle-readout below already shows the runway + telemetry source whenever the angle is
  // AVAILABLE, so an always-on provenance strip just duplicates them. Show a compact strip ONLY
  // when the angle is unavailable — the one case where the runway isn't otherwise surfaced on a
  // result (audit: duplicate provenance / result-panel clutter).
  const showProvenance = hasResult && !activeScenario?.angleSummary?.available

  // Telemetry honesty (audit FE-17): sourceId is the raw backend enum and is still
  // set when telemetry WAS resolved but the angle solve failed. Only a genuinely
  // absent source may claim "Telemetry: none"; otherwise name the source via the
  // localized angleSource map (never string-match on translated text).
  const angleSourceId = activeScenario?.angleSummary?.sourceId ?? null
  const provenanceTelemetry = angleSourceId
    ? copy.live.provenanceTelemetryUnused.replace(
        '{source}',
        copy.live.angleSource?.[angleSourceId] ?? angleSourceId,
      )
    : copy.live.provenanceTelemetryNone

  return (
    <aside className="analysis-panel" id="analysis-details" aria-busy={isAnalyzing}>
      {hasResult ? (
        <>
          {showProvenance && (
            <div className="result-provenance">
              <span className="result-provenance__heading">{copy.live.provenanceHeading}</span>
              <span className="result-provenance__item">
                {copy.live.runwayUsed.replace('{runway}', usedRunwayLabel)}
              </span>
              <span className="result-provenance__item">{provenanceTelemetry}</span>
            </div>
          )}

          {/* Honest partial-result banner: the backend stamps truncated_at_frame when a
              video/sequence out-ran the frame limit mid-stream (container metadata lied),
              so the verdict below covers only the processed prefix (audit B2). */}
          {activeScenario.rawResult?.truncated_at_frame != null && (
            <p className="result-truncation" role="alert">
              {copy.live.truncatedAnalysis.replace(
                '{frames}',
                activeScenario.rawResult.truncated_at_frame,
              )}
            </p>
          )}

          {/* The opposite partial-result case: the source ended EARLY (mid-stream
              decode failure / unreadable sequence images), so the backend stamps
              decode_shortfall = promised-but-undecoded frame count. */}
          {activeScenario.rawResult?.decode_shortfall != null && (
            <p className="result-truncation" role="alert">
              {copy.live.decodeShortfall
                .replace('{decoded}', activeScenario.rawResult.frame_count)
                .replace(
                  '{expected}',
                  activeScenario.rawResult.frame_count +
                    activeScenario.rawResult.decode_shortfall,
                )}
            </p>
          )}

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

          {(activeScenario.rawResult?.model_label || activeScenario.rawResult?.model_id) && (
            <div className="model-readout">
              <span>{copy.live.modelUsed}</span>
              <strong>{activeScenario.rawResult.model_label || activeScenario.rawResult.model_id}</strong>
              {activeScenario.rawResult.model_role && (
                <p>
                  {copy.live.modelRole?.[activeScenario.rawResult.model_role] ??
                    activeScenario.rawResult.model_role}
                </p>
              )}
            </div>
          )}

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
              {/* Total count up front: the list itself scrolls inside a capped
                  box (a long sweep produces dozens of flips), so the size of
                  the evidence must be readable without scrolling. */}
              <small className="transition-readout__count tnum">
                {activeScenario.transitions.length}
              </small>
              <ul>
                {activeScenario.transitions.map((event, index) => {
                  const seconds = canSeekVideo ? frameToSeconds(event.frame_index) : null
                  const timeLabel = seconds != null ? formatVideoTime(seconds) : null
                  return (
                    <li key={`${event.lamp_index}-${event.frame_index}-${index}`}>
                      <span className="transition-readout__event">
                        {`${copy.live.light} ${event.lamp_index}: `}
                        {`${copy.status?.[event.from_state] ?? event.from_state} → ${copy.status?.[event.to_state] ?? event.to_state}`}
                        {/* The flip's viewing angle is the actual evidence (which set
                            angle the lamp crossed) — show it whenever the backend
                            resolved one. The frame alone would be cryptic; angles are
                            what the PAPI verification workflow reasons in. */}
                        {event.elevation_angle_deg != null && (
                          <span className="transition-readout__angle tnum">
                            {` · ${Number(event.elevation_angle_deg).toFixed(2)}°`}
                          </span>
                        )}
                      </span>
                      {/* Clickable timestamp: seeks (and pauses) the stage video at
                          this flip so the evidence can be eyeballed immediately. */}
                      {timeLabel && (
                        <button
                          type="button"
                          className="transition-readout__jump mono"
                          onClick={() => requestFrameSeek(event.frame_index)}
                          aria-label={copy.live.seekTransition.replace('{time}', timeLabel)}
                        >
                          <Play size={10} aria-hidden="true" />
                          {timeLabel}
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </>
      ) : (
        <div className="analysis-empty">
          <span className="empty-state__icon">
            <Radar size={26} aria-hidden="true" />
          </span>
          <p>{copy.live.emptyState}</p>
        </div>
      )}
    </aside>
  )
}
