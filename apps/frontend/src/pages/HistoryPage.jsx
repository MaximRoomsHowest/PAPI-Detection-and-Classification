import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import {
  downloadLogsCsv,
  fetchLogDetail,
  fetchLogs,
  fetchModelInfo,
  fetchModels,
  fetchStats,
  resolveMediaUrl,
  revokeMediaUrl,
} from '../lib/api'
import { localizedErrorMessage } from '../lib/errorMessages'
import { useModalA11y } from '../hooks/useModalA11y'
import { useLiveDemo } from '../context/liveDemoContext'
import { HistoryStats } from '../components/history/HistoryStats'
import { HistoryFilters } from '../components/history/HistoryFilters'
import { HistoryTable } from '../components/history/HistoryTable'
import { HistoryDetailModal } from '../components/history/HistoryDetailModal'

const HISTORY_PAGE_SIZE = 25

// The six list filters travel together: every change shares one transition
// (close the modal, mark the refetch, jump back to page 1), so they live in a
// single state object with one change handler instead of six parallel useStates.
const EMPTY_FILTERS = {
  runway: '',
  state: '',
  model: '',
  media: '',
  // YYYY-MM-DD from the date input; sent as created_after (date-only ISO is
  // read as UTC midnight by the backend, matching the stored-UTC convention).
  date: '',
  // One of '' | '0.5' | '0.75' | '0.9' (the select buckets in HistoryFilters).
  confidence: '',
}

// The date input yields a bare YYYY-MM-DD, which the backend reads as UTC
// midnight. A user east of UTC picking "today" would silently lose their
// early-morning rows (local 00:00–02:00 is still "yesterday" in UTC), so the
// LOCAL midnight is converted to a full UTC instant before it is sent.
function createdAfterInstant(dateValue) {
  return dateValue ? new Date(`${dateValue}T00:00:00`).toISOString() : undefined
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
  // Shared runway list (labels for the runway column + filter) comes from the
  // Live-Demo provider, same source the selector and Runways page use.
  const { runways = [] } = useLiveDemo()
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [modelInfo, setModelInfo] = useState(null)
  const [stats, setStats] = useState(null)
  const [selectedLog, setSelectedLog] = useState(null)
  const [openingLogId, setOpeningLogId] = useState(null)
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
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(0)
  // Read in the fetch effects' dependency arrays: bumping it forces a refetch
  // even when no filter or page changed (the manual Refresh button).
  const [refreshKey, setRefreshKey] = useState(0)

  // Stable universe of filter options (audit F18/F20). The /api/stats counts are
  // themselves filtered by the active runway/state, so deriving the dropdown
  // options straight from them makes the currently-selected option (and others)
  // vanish after a selection. Instead we accumulate every runway id / state key
  // ever seen into these sorted lists and feed the dropdowns from there, so the
  // option list only ever grows and the active selection never disappears.
  const [runwayOptions, setRunwayOptions] = useState([])
  const [stateOptions, setStateOptions] = useState([])
  const [modelOptions, setModelOptions] = useState([])

  // Model info changes rarely, so fetch it once on mount rather than on every
  // refresh or filter change (audit IMP-FE-19). A failure here is non-critical —
  // the model card just renders "Unavailable". The registry list seeds the model
  // filter options the same way (logs from since-removed models are folded in by
  // the logs effect below, so the dropdown can still name them).
  useEffect(() => {
    let ignore = false
    fetchModelInfo()
      .then((info) => {
        if (!ignore) setModelInfo(info)
      })
      .catch(() => {})
    fetchModels()
      .then((models) => {
        if (ignore || !Array.isArray(models)) return
        const ids = models.map((model) => model?.model_id).filter(Boolean)
        setModelOptions((prev) => mergeOptions(prev, ids, null))
      })
      .catch(() => {})
    return () => {
      ignore = true
    }
  }, [])

  // Fetch logs whenever the page, a filter, or the manual refresh key changes.
  // Every setState runs in an async callback after the awaited fetch (never
  // synchronously in the effect body), so there is no set-state cascade.
  useEffect(() => {
    let ignore = false
    const options = {
      limit: HISTORY_PAGE_SIZE,
      offset: page * HISTORY_PAGE_SIZE,
      runwayId: filters.runway || undefined,
      globalState: filters.state || undefined,
      modelId: filters.model || undefined,
      mediaType: filters.media || undefined,
      createdAfter: createdAfterInstant(filters.date),
      minConfidence: filters.confidence ? Number(filters.confidence) : undefined,
    }
    fetchLogs(options)
      .then((logsResult) => {
        if (ignore) return
        setLogs(logsResult.items)
        setTotal(logsResult.total)
        // /api/stats has no by_model breakdown; fold in the ids seen on this
        // page of logs so since-removed models stay selectable alongside the
        // registry-seeded options from the mount effect.
        setModelOptions((prev) =>
          mergeOptions(
            prev,
            logsResult.items.map((item) => item?.model_id).filter(Boolean),
            filters.model,
          ),
        )
      })
      .catch((loadError) => {
        if (!ignore) setError(localizedErrorMessage(loadError, copy))
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
    // `copy` is only read to localize a failure message inside the catch; a
    // locale switch must NOT refetch the logs, so it is intentionally omitted
    // (the banner simply renders in the locale active at failure time).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filters, refreshKey])

  // Stats describe the filtered slice, so they refetch on filter/refresh
  // changes only — paging through results cannot change the aggregate, so it
  // no longer triggers a stats round-trip.
  useEffect(() => {
    let ignore = false
    fetchStats({
      runwayId: filters.runway || undefined,
      globalState: filters.state || undefined,
      modelId: filters.model || undefined,
      mediaType: filters.media || undefined,
      createdAfter: createdAfterInstant(filters.date),
      minConfidence: filters.confidence ? Number(filters.confidence) : undefined,
    })
      .then((nextStats) => {
        if (ignore) return
        setStats(nextStats)
        // Grow the stable filter-option universe from this response. We union
        // (never replace) so options survive a narrowing filter selection, and
        // we fold in the active selections so they stay present even if the
        // backend has stopped reporting them. Returning the previous array
        // unchanged when nothing is new avoids a needless re-render.
        setRunwayOptions((prev) =>
          mergeOptions(prev, Object.keys(nextStats?.by_runway ?? {}), filters.runway),
        )
        setStateOptions((prev) =>
          mergeOptions(prev, Object.keys(nextStats?.by_global_state ?? {}), filters.state),
        )
      })
      .catch((loadError) => {
        // The logs effect fires on the same triggers and reports its own
        // failure; don't let whichever request resolves LAST overwrite the
        // other's message — first error wins, refetch clears it.
        if (!ignore) setError((current) => current || localizedErrorMessage(loadError, copy))
      })
    return () => {
      ignore = true
    }
    // `copy` intentionally omitted — same rationale as the logs effect above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, refreshKey])

  // Refresh jumps back to page 1 so freshly-logged analyses (newest first) are
  // visible, and forces a refetch via refreshKey even when already on page 1.
  const handleRefresh = () => {
    setError('')
    setIsRefreshing(true)
    setPage(0)
    setRefreshKey((key) => key + 1)
  }

  const closeModal = useCallback(() => setSelectedLog(null), [])

  // Mark a refetch in flight from the handlers that trigger it (filter change,
  // pagination) rather than inside the effect — keeps the loading cue + pagination
  // gating without a synchronous setState in the effect body. The effect's
  // finally() always clears it (audit FB-01/FB-02). Each also closes the detail
  // modal: the fixed backdrop normally makes them unreachable while it is open,
  // but if focus ever escapes the trap (browser chrome re-entry) the modal must
  // not sit over a list it no longer belongs to. No-op when already closed.
  const handleFilterChange = (field) => (event) => {
    closeModal()
    setIsFetching(true)
    setPage(0)
    const value = event.target.value
    setFilters((current) => ({ ...current, [field]: value }))
  }

  const hasActiveFilters = Object.values(filters).some(Boolean)

  // Clear filters (audit F18) — reset the selects and return to page 1. A
  // refetch follows automatically because the filter state changed.
  const handleClearFilters = () => {
    closeModal()
    setIsFetching(true)
    setPage(0)
    setFilters(EMPTY_FILTERS)
  }

  const handleExportCsv = async () => {
    setIsExporting(true)
    setError('')
    try {
      // Filter-aware filename so a filtered export isn't indistinguishable from a
      // full export once downloaded (audit FB-08).
      const nameParts = [
        'papi_analysis_logs',
        filters.runway,
        filters.state,
        filters.model,
        filters.media,
        filters.date && `from_${filters.date}`,
        filters.confidence && `conf_${Math.round(Number(filters.confidence) * 100)}`,
      ].filter(Boolean)
      await downloadLogsCsv(
        {
          runwayId: filters.runway || undefined,
          globalState: filters.state || undefined,
          modelId: filters.model || undefined,
          mediaType: filters.media || undefined,
          createdAfter: createdAfterInstant(filters.date),
          minConfidence: filters.confidence ? Number(filters.confidence) : undefined,
        },
        `${nameParts.join('_')}.csv`,
      )
    } catch (exportError) {
      setError(localizedErrorMessage(exportError, copy))
    } finally {
      setIsExporting(false)
    }
  }

  const isBusy = isLoading || isRefreshing || isFetching
  const pageStart = total === 0 ? 0 : page * HISTORY_PAGE_SIZE + 1
  const pageEnd = Math.min(total, (page + 1) * HISTORY_PAGE_SIZE)

  const openLog = async (logId) => {
    // The row buttons stay focusable while a detail loads (aria-disabled, not
    // disabled — see HistoryTable), so guard re-entry here instead.
    if (openingLogId != null) return
    setError('')
    setShowRaw(false)
    setOpeningLogId(logId)
    try {
      const detail = await fetchLogDetail(logId)
      setSelectedLog(detail)
    } catch (detailError) {
      setError(localizedErrorMessage(detailError, copy))
    } finally {
      setOpeningLogId(null)
    }
  }

  const modalRef = useRef(null)

  // Modal a11y/UX (audit IMP-FE-11): close on Escape, move focus into the dialog
  // on open, and restore focus to the trigger on close.
  useModalA11y(modalRef, Boolean(selectedLog), closeModal)

  // Resolve the modal's annotated artifact through resolveMediaUrl so it still loads
  // when an API key is configured: a bare /media <img>/<video> src can't send the
  // X-API-Key header (→ 401). resolveMediaUrl fetches it once and hands back an object
  // URL, and returns the plain URL untouched when no key is set (no-op in the keyless
  // demo). Keyed by artifact_url so a stale blob is never shown for a newly-opened log,
  // and revoked on close/change to avoid leaks. All setState stays in the async
  // callbacks (never synchronously in the effect body) per the page's render-cascade
  // rule (audit C1).
  const [artifact, setArtifact] = useState({ key: null, url: null })
  useEffect(() => {
    const key = selectedLog?.artifact_url ?? null
    let active = true
    let resolved = null
    resolveMediaUrl(key)
      .then((url) => {
        if (!active) {
          revokeMediaUrl(url)
          return
        }
        resolved = url
        setArtifact({ key, url })
      })
      .catch(() => {
        if (active) setArtifact({ key, url: null })
      })
    return () => {
      active = false
      revokeMediaUrl(resolved)
    }
  }, [selectedLog])

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

      <HistoryStats modelInfo={modelInfo} stats={stats} isFiltered={hasActiveFilters} copy={copy} />

      <HistoryFilters
        runwayFilter={filters.runway}
        stateFilter={filters.state}
        modelFilter={filters.model}
        mediaFilter={filters.media}
        dateFilter={filters.date}
        confidenceFilter={filters.confidence}
        runwayOptions={runwayOptions}
        stateOptions={stateOptions}
        modelOptions={modelOptions}
        hasActiveFilters={hasActiveFilters}
        onRunwayChange={handleFilterChange('runway')}
        onStateChange={handleFilterChange('state')}
        onModelChange={handleFilterChange('model')}
        onMediaChange={handleFilterChange('media')}
        onDateChange={handleFilterChange('date')}
        onConfidenceChange={handleFilterChange('confidence')}
        onClearFilters={handleClearFilters}
        onExportCsv={handleExportCsv}
        isExporting={isExporting}
        isBusy={isBusy}
        total={total}
        runways={runways}
        copy={copy}
      />

      <HistoryTable
        logs={logs}
        isLoading={isLoading}
        isBusy={isBusy}
        hasActiveFilters={hasActiveFilters}
        openLog={openLog}
        openingLogId={openingLogId}
        page={page}
        total={total}
        pageStart={pageStart}
        pageEnd={pageEnd}
        onPrev={() => {
          closeModal()
          setIsFetching(true)
          setPage((current) => Math.max(0, current - 1))
        }}
        onNext={() => {
          closeModal()
          setIsFetching(true)
          setPage((current) => current + 1)
        }}
        runways={runways}
        copy={copy}
      />

      {selectedLog && (
        <HistoryDetailModal
          selectedLog={selectedLog}
          artifact={artifact}
          showRaw={showRaw}
          onToggleRaw={() => setShowRaw((open) => !open)}
          onClose={closeModal}
          modalRef={modalRef}
          runways={runways}
          copy={copy}
        />
      )}
    </section>
  )
}
