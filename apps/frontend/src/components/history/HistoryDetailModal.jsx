import clsx from 'clsx'
import { History as HistoryIcon, X } from 'lucide-react'
import { formatAngle, percent } from '../../lib/format'
import { runwayDisplayName } from '../../lib/runwaySelection'

// Mirrors the backend's DETECTION_CLASS_TO_STATE (apps/backend/app/services/state.py)
// so the compact detections summary shows a readable lamp colour instead of a
// bare class id. Kept tiny and explicit — falls through to the raw id otherwise.
const DETECTION_CLASS_LABEL = { 0: 'red', 1: 'white' }

function detectionLabel(detection) {
  const classId = detection?.class_id
  if (classId != null && DETECTION_CLASS_LABEL[classId]) return DETECTION_CLASS_LABEL[classId]
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

  return (
    <div className="history-modal-backdrop">
      {/* Click-the-backdrop-to-dismiss as a real, keyboard-focusable control
          instead of an onClick on a non-interactive <div> (which had no
          keyboard path). It sits behind the dialog as a full-bleed layer;
          Escape also closes via useModalA11y, and the focus trap keeps Tab
          inside the dialog. Inline-positioned because CSS for this overlay
          lives elsewhere and this component owns no stylesheet. */}
      <button
        type="button"
        className="history-modal-dismiss"
        aria-label={copy.history.close}
        onClick={onClose}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          border: 0,
          padding: 0,
          margin: 0,
          background: 'transparent',
          cursor: 'default',
        }}
      />
      <section
        className="history-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-detail-title"
        ref={modalRef}
        tabIndex={-1}
        // position:relative so the dialog paints above the absolutely-
        // positioned backdrop-dismiss button (which would otherwise stack on
        // top and swallow clicks). The .history-modal CSS sets no position,
        // so this is purely additive.
        style={{ position: 'relative' }}
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
            <strong>{selectedLog.global_state?.replaceAll('_', ' ') ?? '—'}</strong>
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
        </div>

        {artifact.key === selectedLog.artifact_url && artifact.url && (
          <div className="history-artifact">
            {selectedLog.media_type === 'video' ? (
              <video src={artifact.url} controls>
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
                  <span className="tnum">L{lamp.index}</span> · {lamp.state} · <span className="tnum">{percent(lamp.confidence)}%</span>
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
                      <td>{detectionLabel(detection)}</td>
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

        <div className="history-angle-note">
          <HistoryIcon size={16} />
          <span>{copy.history.angleNote}</span>
          <p>{selectedLog.angle?.angle_note ?? copy.history.unavailable}</p>
        </div>
      </section>
    </div>
  )
}
