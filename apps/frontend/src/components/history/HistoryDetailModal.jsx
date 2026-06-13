import clsx from 'clsx'
import { History as HistoryIcon, X } from 'lucide-react'
import { formatAngle, percent } from '../../lib/format'
import { transitionEventsForResult } from '../../lib/insightsTransforms'
import { runwayDisplayName } from '../../lib/runwaySelection'
import { globalStateLabel, lampStateLabel } from '../../lib/stateLabels'

// Mirrors the backend's DETECTION_CLASS_TO_STATE (apps/backend/app/services/state.py)
// so the compact detections summary shows a readable lamp colour instead of a
// bare class id. Kept tiny and explicit — falls through to the raw id otherwise.
const DETECTION_CLASS_STATE = { 0: 'red', 1: 'white' }

function detectionLabel(detection, copy) {
  const classId = detection?.class_id
  if (classId != null && DETECTION_CLASS_STATE[classId]) {
    return lampStateLabel(DETECTION_CLASS_STATE[classId], copy)
  }
  if (classId != null) return `class ${classId}`
  return '—'
}

// The log-detail dialog: the state/confidence/angle/processing grid, the annotated
// artifact, per-lamp colours, the detections summary + raw-JSON disclosure, and the
// angle note. Rendered only when a log is selected; the parent owns selection +
// artifact resolution + the focus-trap ref and passes onClose / onToggleRaw down.
export function HistoryDetailModal({
  selectedLog,
  artifact,
  showRaw,
  onToggleRaw,
  onClose,
  modalRef,
  runways,
  copy,
}) {
  const detections = selectedLog?.detections ?? []
  const transitions = transitionEventsForResult(selectedLog)

  return (
    <div className="history-modal-backdrop">
      {/* Click-the-backdrop-to-dismiss as a real, keyboard-focusable control
          instead of an onClick on a non-interactive <div> (which had no
          keyboard path). It sits behind the dialog as a full-bleed layer
          (.history-modal-dismiss); Escape also closes via useModalA11y, and
          the focus trap keeps Tab inside the dialog. */}
      <button
        type="button"
        className="history-modal-dismiss"
        aria-label={copy.history.close}
        onClick={onClose}
      />
      <section
        className="history-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-detail-title"
        ref={modalRef}
        tabIndex={-1}
      >
        <div className="history-modal-heading">
          <div>
            <p className="eyebrow">{copy.history.detailTitle}</p>
            <h3 id="history-detail-title">{selectedLog.original_filename}</h3>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label={copy.history.close}
          >
            <X size={18} />
          </button>
        </div>

        <div className="history-detail-grid">
          <div>
            <span>{copy.history.state}</span>
            <strong>{globalStateLabel(selectedLog.global_state, copy) || '—'}</strong>
          </div>
          <div>
            <span>{copy.history.runway}</span>
            <strong title={selectedLog.runway_id}>
              {runwayDisplayName(selectedLog.runway_id, runways)}
            </strong>
          </div>
          <div>
            <span>{copy.history.confidence}</span>
            <strong className="tnum">{percent(selectedLog.confidence)}%</strong>
          </div>
          <div>
            <span>{copy.history.angle}</span>
            {/* Mirror the table's honesty guard: only show a reading when the
                metadata actually yielded one, else the unavailable fallback —
                a stale finite 0 would otherwise read as a real angle (audit FB-04). */}
            <strong className="tnum">
              {selectedLog.angle?.angle_available && selectedLog.angle?.elevation_angle_deg != null
                ? formatAngle(selectedLog.angle.elevation_angle_deg)
                : copy.history.unavailable}
            </strong>
          </div>
          <div>
            <span>{copy.history.processing}</span>
            <strong className="tnum">{selectedLog.processing_ms} ms</strong>
          </div>
          {/* The model that PRODUCED this persisted result — without it an old
              row is indistinguishable from a re-run with another detector
              (integration audit 2026-06-11: stored but never shown). */}
          {(selectedLog.model_label || selectedLog.model_id) && (
            <div>
              <span>{copy.live.modelUsed}</span>
              <strong>{selectedLog.model_label || selectedLog.model_id}</strong>
            </div>
          )}
          <div>
            <span>{copy.history.media}</span>
            <strong>
              {selectedLog.media_type === 'video'
                ? copy.history.mediaVideo
                : copy.history.mediaImage}
              {selectedLog.frame_count > 1 ? ` · ${selectedLog.frame_count}` : ''}
            </strong>
          </div>
          {selectedLog.drone_id && (
            <div>
              <span>{copy.history.drone}</span>
              <strong className="mono">{selectedLog.drone_id}</strong>
            </div>
          )}
        </div>

        {/* Honest partial-result banner, same contract as the Live Demo panel:
            the verdict covers only frames [0, truncated_at_frame). */}
        {selectedLog.truncated_at_frame != null && (
          <p className="result-truncation" role="alert">
            {copy.live.truncatedAnalysis.replace('{frames}', selectedLog.truncated_at_frame)}
          </p>
        )}

        {/* Decode shortfall: the source ended early (damaged file / unreadable
            sequence images) — fewer frames decoded than the source promised. */}
        {selectedLog.decode_shortfall != null && (
          <p className="result-truncation" role="alert">
            {copy.live.decodeShortfall
              .replace('{decoded}', selectedLog.frame_count)
              .replace('{expected}', selectedLog.frame_count + selectedLog.decode_shortfall)}
          </p>
        )}

        {artifact.key === selectedLog.artifact_url && artifact.url && (
          <div className="history-artifact">
            {selectedLog.media_type === 'video' ? (
              <video src={artifact.url} controls aria-label={selectedLog.original_filename}>
                <track kind="captions" />
              </video>
            ) : (
              <img src={artifact.url} alt={selectedLog.original_filename} />
            )}
          </div>
        )}

        <div className="history-modal-columns">
          <div>
            <h4>{copy.history.lamps}</h4>
            <div className="history-lamps">
              {(selectedLog.lamps ?? []).map((lamp) => (
                <span className={clsx('history-lamp', `history-lamp-${lamp.state}`)} key={lamp.index}>
                  <span className="tnum">L{lamp.index}</span> · {lampStateLabel(lamp.state, copy)} ·{' '}
                  {/* An inferred lamp's state came from geometry, not the detector —
                      a confidence percentage would be fabricated precision. Same
                      disclosure rule as LampCard on the Live Demo. */}
                  {lamp.inferred ? (
                    <span title={lamp.inference_note ?? undefined}>{copy.live.inferredFromAngle}</span>
                  ) : (
                    <span className="tnum">{percent(lamp.confidence)}%</span>
                  )}
                </span>
              ))}
            </div>
          </div>
          <div>
            <h4>{copy.history.detections}</h4>
            {/* Compact summary table for the common case; the full raw JSON
                sits behind a "Show raw" toggle (audit F19). */}
            {detections.length === 0 ? (
              <p className="history-detections-empty">{copy.history.unavailable}</p>
            ) : (
              <table className="history-detections-table">
                <thead>
                  <tr>
                    <th scope="col">#</th>
                    <th scope="col">{copy.history.state}</th>
                    <th scope="col">{copy.history.confidence}</th>
                  </tr>
                </thead>
                <tbody>
                  {detections.map((detection, index) => (
                    <tr key={detection.track_id ?? index}>
                      <td className="tnum">{index + 1}</td>
                      <td>{detectionLabel(detection, copy)}</td>
                      <td className="tnum">
                        {Number.isFinite(Number(detection.confidence))
                          ? `${percent(detection.confidence)}%`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button
              className="history-raw-toggle"
              type="button"
              onClick={onToggleRaw}
              aria-expanded={showRaw}
              aria-controls="history-raw-detections"
            >
              {showRaw ? copy.history.showRawHide : copy.history.showRaw}
            </button>
            {showRaw && (
              <pre
                id="history-raw-detections"
                className="history-json"
                // tabIndex makes this scrollable region keyboard-focusable so it
                // can be reached and scrolled by keyboard (WCAG 2.1.1). The a11y
                // rule flags tabIndex on non-interactive elements, but a labelled
                // scroll container (role=region + aria-label) is the intended
                // exception.
                // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
                tabIndex={0}
                role="region"
                aria-label={copy.history.showRaw}
              >
                {JSON.stringify(detections, null, 2)}
              </pre>
            )}
          </div>
        </div>

        {/* Detected red<->white transitions — the headline output of a video
            analysis, persisted in the payload but previously invisible here
            (integration audit 2026-06-11). Mirrors the Live Demo readout:
            localized lamp colours + which method produced the events. */}
        {transitions.length > 0 && (
          <div className="history-transitions">
            <span>{copy.live.transitionsHeading}</span>
            {selectedLog.transition_method && (
              <small>
                {copy.live.transitionMethodUsed.replace(
                  '{method}',
                  selectedLog.transition_method === 'model'
                    ? copy.live.transitionMethodModel
                    : copy.live.transitionMethodTracking,
                )}
              </small>
            )}
            <ul>
              {transitions.map((event, index) => (
                <li key={`${event.lamp_index}-${event.frame_index}-${index}`}>
                  {`${copy.live.light} ${event.lamp_index}: `}
                  {`${lampStateLabel(event.from_state, copy)} → ${lampStateLabel(event.to_state, copy)}`}
                  {` (${copy.history.frames.toLowerCase()} ${event.frame_index})`}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="history-angle-note">
          <HistoryIcon size={16} />
          <span>{copy.history.angleNote}</span>
          <p>{selectedLog.angle?.angle_note ?? copy.history.unavailable}</p>
        </div>
      </section>
    </div>
  )
}
