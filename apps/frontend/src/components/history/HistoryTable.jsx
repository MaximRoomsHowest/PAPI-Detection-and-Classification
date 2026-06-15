import clsx from 'clsx'
import { Link } from 'react-router-dom'
import { formatAngle, formatTimestamp, percent } from '../../lib/format'
import { videoResultSummary } from '../../lib/historyVideoSummary'
import { runwayDisplayName } from '../../lib/runwaySelection'
import { globalStateLabel } from '../../lib/stateLabels'
import { stateLampPattern } from '../../catalog/stateCatalog'
import { PapiGlyph } from '../PapiGlyph'
import { StateDistributionBar } from './StateDistributionBar'

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
                  <th scope="col">{copy.history.insights}</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => {
                  const videoSummary = videoResultSummary(log)
                  const displayState = videoSummary?.globalState ?? log.global_state
                  const displayConfidence = videoSummary?.confidence ?? log.confidence
                  const displayFrameCount = videoSummary?.frameCount ?? log.frame_count
                  return (
                    <tr key={log.id}>
                      <td data-label={copy.history.filename}>
                        {/* aria-disabled, not the disabled attribute, while the detail is
                            loading: disabling would drop focus to <body> BEFORE the modal
                            opens, so useModalA11y would capture body as the "previously
                            focused" element and restore focus there on close (same
                            keep-focusable rationale as FE-8). The click guard lives in
                            openLog. */}
                        <button
                          className="history-link"
                          type="button"
                          onClick={() => openLog(log.id)}
                          aria-disabled={openingLogId === log.id}
                        >
                          {log.original_filename}
                        </button>
                      </td>
                      <td data-label={copy.history.runway} title={log.runway_id}>
                        {runwayDisplayName(log.runway_id, runways)}
                      </td>
                      <td data-label={copy.history.state}>
                        <div className="history-state-cell">
                          {/* For a video the pill is the DOMINANT (most-frequent)
                              frame state, not a single reading — the hint says so,
                              and the distribution bar below shows the full mix so a
                              clip is visibly distinct from a still image. */}
                          <span
                            className="history-state"
                            title={
                              log.media_type === 'video'
                                ? copy.history.videoStateHint.replace('{frames}', displayFrameCount)
                                : undefined
                            }
                          >
                            {stateLampPattern[displayState] && (
                              <PapiGlyph size="sm" states={stateLampPattern[displayState]} />
                            )}
                            <span className={clsx('state-pill', `state-pill-${displayState}`)}>
                              {globalStateLabel(displayState, copy)}
                            </span>
                          </span>
                          {log.media_type === 'video' && log.state_counts && (
                            <StateDistributionBar
                              counts={log.state_counts}
                              copy={copy}
                              compact
                              className="history-row-dist"
                            />
                          )}
                        </div>
                      </td>
                      <td data-label={copy.history.confidence} className="tnum">
                        {percent(displayConfidence)}%
                      </td>
                      <td data-label={copy.history.angle} className="history-col-secondary tnum">
                        {/* Only the angle of a row whose metadata actually yielded a
                            measurement is shown; "0.000°" for an unmeasured row would
                            read as a real reading, so we render an em-dash instead —
                            matching the Live Demo's "Angle unavailable" honesty. */}
                        {log.angle_available && log.elevation_angle_deg != null
                          ? formatAngle(log.elevation_angle_deg)
                          : '—'}
                      </td>
                      <td data-label={copy.history.frames} className="history-col-secondary tnum">
                        {displayFrameCount}
                        {/* Partial-result badge: the backend mirrors truncated_at_frame /
                            decode_shortfall into the list payload so a capped or
                            half-decoded analysis is visible without opening the row. */}
                        {(log.truncated_at_frame != null || log.decode_shortfall != null) && (
                          <span className="history-partial-badge" title={copy.history.partialBadgeHint}>
                            {copy.history.partialBadge}
                          </span>
                        )}
                      </td>
                      <td data-label={copy.history.processing} className="history-col-secondary tnum">{log.processing_ms} ms</td>
                      <td data-label={copy.history.created} className="tnum">{formatTimestamp(log.created_at, copy.locale)}</td>
                      <td data-label={copy.history.artifact}>
                        {log.artifact_url ? (
                          <button
                            className="history-link"
                            type="button"
                            onClick={() => openLog(log.id)}
                            aria-disabled={openingLogId === log.id}
                          >
                            {copy.history.view}
                          </button>
                        ) : (
                          copy.history.unavailable
                        )}
                      </td>
                      <td data-label={copy.history.insights}>
                        {/* Router Link, not a raw <a>: a hard navigation remounts the
                            whole SPA and wipes the in-memory live-demo session. */}
                        <Link className="history-link" to={`/insights?log=${encodeURIComponent(log.id)}`}>
                          {copy.history.openInsights}
                        </Link>
                      </td>
                    </tr>
                  )
                })}
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
