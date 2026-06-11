import clsx from 'clsx'
import { formatAngle, formatTimestamp, percent } from '../../lib/format'
import { runwayDisplayName } from '../../lib/runwaySelection'
import { globalStateLabel } from '../../lib/stateLabels'

// The analyses table (with its loading/empty states + the horizontal-scroll cue)
// and the pagination controls. Presentational — the parent owns the logs/paging
// state and the openLog handler; onPrev/onNext are pre-bound page steppers.
export function HistoryTable({
  logs,
  isLoading,
  isBusy,
  hasActiveFilters,
  openLog,
  openingLogId,
  page,
  total,
  pageStart,
  pageEnd,
  onPrev,
  onNext,
  runways,
  copy,
}) {
  return (
    <>
      <div
        className={clsx('history-table-wrap', isBusy && !isLoading && 'is-refetching')}
        aria-busy={isBusy}
      >
        {isLoading ? (
          <div className="history-empty" role="status" aria-live="polite">
            {copy.history.loading}
          </div>
        ) : logs.length === 0 ? (
          <div className="history-empty" role="status" aria-live="polite">
            {hasActiveFilters ? copy.history.noMatch : copy.history.empty}
          </div>
        ) : (
          <>
            <table className="history-table">
              <thead>
                <tr>
                  <th scope="col">{copy.history.filename}</th>
                  <th scope="col">{copy.history.runway}</th>
                  <th scope="col">{copy.history.state}</th>
                  <th scope="col">{copy.history.confidence}</th>
                  <th scope="col" className="history-col-secondary">{copy.history.angle}</th>
                  <th scope="col" className="history-col-secondary">{copy.history.frames}</th>
                  <th scope="col" className="history-col-secondary">{copy.history.processing}</th>
                  <th scope="col">{copy.history.created}</th>
                  <th scope="col">{copy.history.artifact}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td data-label={copy.history.filename}>
                      <button className="history-link" type="button" onClick={() => openLog(log.id)} disabled={openingLogId === log.id}>
                        {log.original_filename}
                      </button>
                    </td>
                    <td data-label={copy.history.runway} title={log.runway_id}>
                      {runwayDisplayName(log.runway_id, runways)}
                    </td>
                    <td data-label={copy.history.state}>
                      <span className={clsx('state-pill', `state-pill-${log.global_state}`)}>
                        {globalStateLabel(log.global_state, copy)}
                      </span>
                    </td>
                    <td data-label={copy.history.confidence} className="tnum">{percent(log.confidence)}%</td>
                    <td data-label={copy.history.angle} className="history-col-secondary tnum">
                      {/* Only the angle of a row whose metadata actually yielded a
                          measurement is shown; "0.000°" for an unmeasured row would
                          read as a real reading, so we render an em-dash instead —
                          matching the Live Demo's "Angle unavailable" honesty. */}
                      {log.angle_available && log.elevation_angle_deg != null
                        ? formatAngle(log.elevation_angle_deg)
                        : '—'}
                    </td>
                    <td data-label={copy.history.frames} className="history-col-secondary tnum">{log.frame_count}</td>
                    <td data-label={copy.history.processing} className="history-col-secondary tnum">{log.processing_ms} ms</td>
                    <td data-label={copy.history.created} className="tnum">{formatTimestamp(log.created_at)}</td>
                    <td data-label={copy.history.artifact}>
                      {log.artifact_url ? (
                        <button
                          className="history-link"
                          type="button"
                          onClick={() => openLog(log.id)}
                          disabled={openingLogId === log.id}
                        >
                          {copy.history.view}
                        </button>
                      ) : (
                        copy.history.unavailable
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="history-scroll-cue" aria-hidden="true">
              {copy.history.runway} · {copy.history.state} · {copy.history.confidence} →
            </p>
          </>
        )}
      </div>

      {!isLoading && total > 0 && (
        <div className="history-pagination">
          <button
            className="secondary-button"
            type="button"
            disabled={page === 0 || isBusy}
            onClick={onPrev}
          >
            {copy.history.prev}
          </button>
          <span className="tnum">{`${copy.history.showing} ${pageStart}–${pageEnd} / ${total}`}</span>
          <button
            className="secondary-button"
            type="button"
            disabled={pageEnd >= total || isBusy}
            onClick={onNext}
          >
            {copy.history.next}
          </button>
        </div>
      )}
    </>
  )
}
