import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, History as HistoryIcon, RefreshCw, X } from 'lucide-react'
import clsx from 'clsx'
import {
  downloadLogsCsv,
  fetchLogDetail,
  fetchLogs,
  fetchModelInfo,
  fetchStats,
  mediaUrl,
} from '../lib/api'
import { formatAngle, formatTimestamp, percent } from '../lib/format'
import { useModalA11y } from '../hooks/useModalA11y'

const HISTORY_PAGE_SIZE = 25

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

// Union the existing sorted option list with the incoming keys plus the active
// selection, returning the same array reference when nothing changed so React
// can bail out of the state update (audit F18/F20).
function mergeOptions(previous, incoming, active) {
  const next = new Set(previous)
  for (const value of incoming) next.add(value)
  if (active) next.add(active)
  if (next.size === previous.length) return previous
  return [...next].sort()
}

export function HistoryPage({ copy }) {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [modelInfo, setModelInfo] = useState(null)
  const [stats, setStats] = useState(null)
  const [selectedLog, setSelectedLog] = useState(null)
  const [showRaw, setShowRaw] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  // True only while a filter/page refetch is in flight (initial load uses
  // isLoading, manual refresh uses isRefreshing). Drives aria-busy + the dim
  // cue + pagination gating so a background refetch isn't invisible and Next/Prev
  // can't be double-fired against a stale total (audit FB-01/FB-02).
  const [isFetching, setIsFetching] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [error, setError] = useState('')
  const [runwayFilter, setRunwayFilter] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [page, setPage] = useState(0)
  const [refreshKey, setRefreshKey] = useState(0)

  // Stable universe of filter options (audit F18/F20). The /api/stats counts are
  // themselves filtered by the active runway/state, so deriving the dropdown
  // options straight from them makes the currently-selected option (and others)
  // vanish after a selection. Instead we accumulate every runway id / state key
  // ever seen into these sorted lists and feed the dropdowns from there, so the
  // option list only ever grows and the active selection never disappears.
  const [runwayOptions, setRunwayOptions] = useState([])
  const [stateOptions, setStateOptions] = useState([])

  // Model info changes rarely, so fetch it once on mount rather than on every
  // refresh or filter change (audit IMP-FE-19). A failure here is non-critical —
  // the model card just renders "Unavailable".
  useEffect(() => {
    let ignore = false
    fetchModelInfo()
      .then((info) => {
        if (!ignore) setModelInfo(info)
      })
      .catch(() => {})
    return () => {
      ignore = true
    }
  }, [])

  // Fetch logs + stats whenever the page, a filter, or the manual refresh key
  // changes. Every setState runs in an async callback after the awaited fetch
  // (never synchronously in the effect body), so there is no set-state cascade
  // and the previous setTimeout(0) workaround is no longer needed.
  useEffect(() => {
    let ignore = false
    const options = {
      limit: HISTORY_PAGE_SIZE,
      offset: page * HISTORY_PAGE_SIZE,
      runwayId: runwayFilter || undefined,
      globalState: stateFilter || undefined,
    }
    Promise.all([fetchLogs(options), fetchStats()])
      .then(([logsResult, nextStats]) => {
        if (ignore) return
        setLogs(logsResult.items)
        setTotal(logsResult.total)
        setStats(nextStats)
        // Grow the stable filter-option universe from this response. We union
        // (never replace) so options survive a narrowing filter selection, and
        // we fold in the active selections so they stay present even if the
        // backend has stopped reporting them (e.g. all matching rows moved to
        // another page). Returning the previous array unchanged when nothing is
        // new avoids a needless re-render.
        setRunwayOptions((prev) =>
          mergeOptions(prev, Object.keys(nextStats?.by_runway ?? {}), runwayFilter),
        )
        setStateOptions((prev) =>
          mergeOptions(prev, Object.keys(nextStats?.by_global_state ?? {}), stateFilter),
        )
      })
      .catch((loadError) => {
        if (!ignore) setError(loadError.message)
      })
      .finally(() => {
        if (ignore) return
        setIsLoading(false)
        setIsRefreshing(false)
        setIsFetching(false)
      })
    return () => {
      ignore = true
    }
  }, [page, runwayFilter, stateFilter, refreshKey])

  // Refresh jumps back to page 1 so freshly-logged analyses (newest first) are
  // visible, and forces a refetch via refreshKey even when already on page 1.
  const handleRefresh = () => {
    setError('')
    setIsRefreshing(true)
    setPage(0)
    setRefreshKey((key) => key + 1)
  }

  // Mark a refetch in flight from the handlers that trigger it (filter change,
  // pagination) rather than inside the effect — keeps the loading cue + pagination
  // gating without a synchronous setState in the effect body. The effect's
  // finally() always clears it (audit FB-01/FB-02).
  const handleFilterChange = (setter) => (event) => {
    setIsFetching(true)
    setPage(0)
    setter(event.target.value)
  }

  const hasActiveFilters = Boolean(runwayFilter || stateFilter)

  // Clear filters (audit F18) — reset both selects and return to page 1. A
  // refetch follows automatically because the filter state changed.
  const handleClearFilters = () => {
    setIsFetching(true)
    setPage(0)
    setRunwayFilter('')
    setStateFilter('')
  }

  const handleExportCsv = async () => {
    setIsExporting(true)
    setError('')
    try {
      await downloadLogsCsv({
        runwayId: runwayFilter || undefined,
        globalState: stateFilter || undefined,
      })
    } catch (exportError) {
      setError(exportError.message)
    } finally {
      setIsExporting(false)
    }
  }

  const isBusy = isLoading || isRefreshing || isFetching
  const pageStart = total === 0 ? 0 : page * HISTORY_PAGE_SIZE + 1
  const pageEnd = Math.min(total, (page + 1) * HISTORY_PAGE_SIZE)

  const openLog = async (logId) => {
    setError('')
    setShowRaw(false)
    try {
      const detail = await fetchLogDetail(logId)
      setSelectedLog(detail)
    } catch (detailError) {
      setError(detailError.message)
    }
  }

  const modalRef = useRef(null)
  const closeModal = useCallback(() => setSelectedLog(null), [])

  // Modal a11y/UX (audit IMP-FE-11): close on Escape, move focus into the dialog
  // on open, and restore focus to the trigger on close.
  useModalA11y(modalRef, Boolean(selectedLog), closeModal)

  const detections = selectedLog?.detections ?? []

  return (
    <section className="history-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.history.eyebrow}</p>
          <h2>{copy.history.title}</h2>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={handleRefresh}
          disabled={isRefreshing}
        >
          <RefreshCw size={18} />
          {isRefreshing ? copy.history.loading : copy.history.refresh}
        </button>
      </div>

      {error && (
        <div className="analysis-status error" role="alert">
          {error}
        </div>
      )}

      <div className="history-summary-grid">
        <div className="history-summary">
          <span>{copy.history.model}</span>
          <strong>{modelInfo?.model_filename ?? copy.history.unavailable}</strong>
          <small>{`${copy.history.trainingRun}: ${modelInfo?.training_run ?? copy.history.unavailable}`}</small>
          {modelInfo?.sha256 && (
            <small className="history-checksum" title={modelInfo.sha256}>
              {`${copy.history.checksum}: `}
              <span className="mono">{`${modelInfo.sha256.slice(0, 12)}…`}</span>
            </small>
          )}
        </div>
        {modelInfo?.val_metrics?.map50_95 != null && (
          <div className="history-summary">
            <span>{copy.history.accuracy}</span>
            <strong className="tnum">{`${(modelInfo.val_metrics.map50_95 * 100).toFixed(1)}%`}</strong>
            <small>{`${modelInfo.dataset_split_evaluated ?? 'val'} split`}</small>
          </div>
        )}
        <div className="history-summary">
          <span>{copy.history.sample}</span>
          <strong className="tnum">{stats?.total_analyses ?? stats?.sample_size ?? 0}</strong>
          <small className="tnum">
            {stats ? `${stats.image_count} image · ${stats.video_count} video` : copy.history.unavailable}
          </small>
        </div>
        <div className="history-summary">
          <span>{copy.history.confidenceAvg}</span>
          <strong className="tnum">{stats?.avg_confidence != null ? `${percent(stats.avg_confidence)}%` : '—'}</strong>
          <small>{copy.history.stats}</small>
        </div>
        <div className="history-summary">
          <span>{copy.history.avg}</span>
          <strong className="tnum">{stats?.avg_processing_ms ?? '—'}</strong>
          <small className="tnum">
            {`${copy.history.p50} ${stats?.p50_processing_ms ?? '—'} · ${copy.history.p95} ${stats?.p95_processing_ms ?? '—'}`}
          </small>
        </div>
      </div>

      <div className="history-controls">
        <select
          className="history-filter"
          value={runwayFilter}
          onChange={handleFilterChange(setRunwayFilter)}
          aria-label={copy.history.runway}
        >
          <option value="">{copy.history.filterRunway}</option>
          {runwayOptions.map((runwayId) => (
            <option key={runwayId} value={runwayId}>
              {runwayId}
            </option>
          ))}
        </select>
        <select
          className="history-filter"
          value={stateFilter}
          onChange={handleFilterChange(setStateFilter)}
          aria-label={copy.history.state}
        >
          <option value="">{copy.history.filterState}</option>
          {stateOptions.map((stateKey) => (
            <option key={stateKey} value={stateKey}>
              {stateKey.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
        {hasActiveFilters && (
          <button
            className="ghost-button"
            type="button"
            onClick={handleClearFilters}
          >
            <X size={16} />
            {copy.history.clearFilters}
          </button>
        )}
        <button
          className="secondary-button"
          type="button"
          onClick={handleExportCsv}
          disabled={isExporting || isBusy || total === 0}
        >
          <Download size={18} />
          {isExporting ? copy.history.exporting : copy.history.exportCsv}
        </button>
      </div>

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
                      <button className="history-link" type="button" onClick={() => openLog(log.id)}>
                        {log.original_filename}
                      </button>
                    </td>
                    <td data-label={copy.history.runway}>{log.runway_id}</td>
                    <td data-label={copy.history.state}>
                      <span className={clsx('state-pill', `state-pill-${log.global_state}`)}>
                        {log.global_state.replaceAll('_', ' ')}
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
                        <a href={mediaUrl(log.artifact_url)} target="_blank" rel="noreferrer">
                          {copy.history.view}
                        </a>
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
            onClick={() => {
              setIsFetching(true)
              setPage((current) => Math.max(0, current - 1))
            }}
          >
            {copy.history.prev}
          </button>
          <span className="tnum">{`${copy.history.showing} ${pageStart}–${pageEnd} / ${total}`}</span>
          <button
            className="secondary-button"
            type="button"
            disabled={pageEnd >= total || isBusy}
            onClick={() => {
              setIsFetching(true)
              setPage((current) => current + 1)
            }}
          >
            {copy.history.next}
          </button>
        </div>
      )}

      {selectedLog && (
        <div
          className="history-modal-backdrop"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) setSelectedLog(null)
          }}
        >
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
                onClick={() => setSelectedLog(null)}
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

            {selectedLog.artifact_url && (
              <div className="history-artifact">
                {selectedLog.media_type === 'video' ? (
                  <video src={mediaUrl(selectedLog.artifact_url)} controls>
                    <track kind="captions" />
                  </video>
                ) : (
                  <img src={mediaUrl(selectedLog.artifact_url)} alt={selectedLog.original_filename} />
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
                  onClick={() => setShowRaw((open) => !open)}
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
      )}
    </section>
  )
}
