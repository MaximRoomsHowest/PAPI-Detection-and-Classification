import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as Tabs from '@radix-ui/react-tabs'
import { Download, FileDown, TriangleAlert, Info, MapPin } from 'lucide-react'
import clsx from 'clsx'
import { AngleVsStateCharts } from '../components/insights/AngleVsStateCharts'
import { TransitionCharts } from '../components/insights/TransitionCharts'
import { SessionSummaryCharts } from '../components/insights/SessionSummaryCharts'
import { ModelMetricsPanel } from '../components/insights/ModelMetricsPanel'
import { InsightsSummaryStrip } from '../components/insights/InsightsSummaryStrip'
import { sessionRunwaySummary } from '../lib/runwaySelection'
import { summarizeSession, transitionCsv } from '../lib/insightsTransforms'
import { fetchLogDetail } from '../lib/api'
import { localizedErrorMessage } from '../lib/errorMessages'
import { formatTimestamp } from '../lib/format'
import { useChartExport } from '../hooks/useChartExport'
import { useFetch } from '../hooks/useFetch'
import { useLiveDemo } from '../context/liveDemoContext'

// Insights is split into two tabs: "Current analysis" (charts built from the
// session's real results — angle-vs-state, transitions, per-light/confidence
// distributions) and "Model & dataset" (aggregate /api/stats + /api/model).
// Both tab panels are force-mounted (CSS parks the inactive one off-screen at
// full size) so PDF export captures every chart and Plotly never re-initialises
// on tab switch.
export function InsightsPage({ plotTheme, copy }) {
  const { backendResults, runways = [] } = useLiveDemo()
  const [searchParams] = useSearchParams()
  const logId = searchParams.get('log')
  const historyLog = useFetch(
    () => (logId ? fetchLogDetail(logId) : Promise.resolve(null)),
    [logId],
  )
  const exportSessionRef = useRef({ results: [], runways: [], selectedRunwayId: null })
  const {
    insightsRef,
    isExporting,
    exportError,
    handleDownloadCharts: onDownloadCharts,
  } = useChartExport(copy, exportSessionRef)

  // Controlled so the off-screen, force-mounted panel can be marked `inert`
  // (removed from the tab order and the a11y tree) while staying in the DOM at
  // full size for PDF export. Plotly.toImage still reads inert nodes.
  const [tab, setTab] = useState('current')
  const sourceMode = logId ? 'history' : 'live'
  const sourceResults = useMemo(
    () => (sourceMode === 'history' ? (historyLog.data ? [historyLog.data] : []) : (backendResults ?? [])),
    [sourceMode, historyLog.data, backendResults],
  )
  const hasSession = (sourceResults?.length ?? 0) > 0
  const hasTransitions = sourceResults?.some((result) => (result?.transitions?.length ?? 0) > 0)
  // At-a-glance roll-up for the verdict strip (lamps crossed / elevation / trust).
  const summary = useMemo(() => summarizeSession(sourceResults), [sourceResults])
  const runwaySummary = sessionRunwaySummary(sourceResults, runways)
  const runwayContextText =
    runwaySummary.kind === 'mixed'
      ? copy.insights.runwayContextMixed.replace('{runways}', runwaySummary.label)
      : runwaySummary.kind === 'single'
        ? copy.insights.runwayContext.replace('{runway}', runwaySummary.label)
        : copy.insights.runwayContextNone
  const shortLogId = logId ? logId.slice(0, 8) : ''
  const sourceLabel =
    sourceMode === 'history'
      ? copy.insights.sourceHistory.replace('{id}', shortLogId)
      : copy.insights.sourceLive
  const sourceTimestamp =
    sourceMode === 'history' && historyLog.data?.created_at
      ? formatTimestamp(historyLog.data.created_at, copy.locale)
      : null

  useEffect(() => {
    const first = sourceResults?.[0]
    exportSessionRef.current = {
      results: sourceResults ?? [],
      runways,
      selectedRunwayId: first?.runway_id ?? null,
      sourceLabel,
      logId: sourceMode === 'history' ? logId : null,
      createdAt: sourceTimestamp,
    }
  }, [sourceResults, runways, sourceLabel, sourceMode, logId, sourceTimestamp])

  const handleDownloadTransitionCsv = () => {
    const csv = transitionCsv(sourceResults, { mode: sourceMode, logId })
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `papi-transition-events-${sourceMode === 'history' ? logId : 'live-session'}.csv`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="insights-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.insights.eyebrow}</p>
          <h2>{copy.insights.title}</h2>
        </div>
        <div className="section-actions">
          {hasSession && (
            <Link className="insights-runway-chip" to="/runways">
              <MapPin size={15} aria-hidden="true" />
              {runwayContextText}
            </Link>
          )}
          {sourceMode === 'history' && (
            <Link className="secondary-button" to="/insights">
              {copy.insights.backToLive}
            </Link>
          )}
          {hasTransitions && (
            <button
              className="secondary-button"
              type="button"
              onClick={handleDownloadTransitionCsv}
            >
              <FileDown size={18} />
              {copy.insights.downloadTransitionsCsv}
            </button>
          )}
          <button
            className={clsx('secondary-button', exportError && 'has-error')}
            type="button"
            onClick={onDownloadCharts}
            // Disabled with no session charts so a first-time click can't produce a
            // misleading PDF of only the aggregate model chart (audit D4).
            disabled={isExporting || !hasSession}
            aria-busy={isExporting}
            title={!hasSession ? copy.insights.downloadNeedsData : undefined}
            aria-label={!hasSession ? copy.insights.downloadNeedsData : copy.insights.download}
          >
            <Download size={18} />
            {isExporting ? copy.insights.preparing : copy.insights.download}
          </button>
          <span className="source-note">{copy.insights.source}</span>
          <span className="source-note">{sourceLabel}</span>
          {sourceTimestamp ? <span className="source-note">{sourceTimestamp}</span> : null}
        </div>
      </div>

      {sourceMode === 'history' && historyLog.loading && (
        <div className="insights-cta" role="status" aria-live="polite">
          <Info size={18} aria-hidden="true" />
          <span>{copy.insights.loadingHistoryLog}</span>
        </div>
      )}

      {sourceMode === 'history' && historyLog.error && (
        <div className="export-status error" role="alert" aria-live="assertive">
          <TriangleAlert size={16} />
          {localizedErrorMessage(historyLog.error, copy)}
          <Link className="text-link" to="/history">
            {copy.insights.backToHistory}
          </Link>
        </div>
      )}

      {exportError && (
        <div className="export-status error" role="alert" aria-live="assertive">
          <TriangleAlert size={16} />
          {exportError}
        </div>
      )}

      {/* No analysis this session: point the user at Live Demo instead of leaving
          them with several empty cards and a working-but-lonely model chart (audit D5). */}
      {!hasSession && !(sourceMode === 'history' && historyLog.loading) && !historyLog.error && (
        <div className="insights-cta" role="note">
          <Info size={18} aria-hidden="true" />
          <span>{copy.insights.emptyCta}</span>
          <Link className="text-link" to="/live-demo">
            {copy.insights.emptyCtaLink}
          </Link>
        </div>
      )}

      {/* Verdict layer: stated before the charts and OUTSIDE the tabs (so it isn't
          parked off-screen with an inactive force-mounted panel). Self-hides when empty. */}
      <InsightsSummaryStrip
        summary={summary}
        sourceMeta={{ label: sourceLabel, timestamp: sourceTimestamp }}
        copy={copy}
      />

      <Tabs.Root value={tab} onValueChange={setTab} className="insights-tabs">
        <Tabs.List className="insights-tab-list" aria-label={copy.insights.eyebrow}>
          <Tabs.Trigger className="insights-tab-trigger" value="current">
            {copy.insights.tabCurrent}
          </Tabs.Trigger>
          <Tabs.Trigger className="insights-tab-trigger" value="model">
            {copy.insights.tabModel}
          </Tabs.Trigger>
        </Tabs.List>

        <div className="insights-tab-viewport" ref={insightsRef}>
          <Tabs.Content
            className="insights-tab-content"
            value="current"
            forceMount
            inert={tab !== 'current'}
            aria-hidden={tab !== 'current'}
          >
            <div className="insights-grid">
              {/* The measured transition angles lead — they are the commissioning
                  deliverable; the per-lamp evidence (state bands, redness sweeps)
                  and session distributions follow. */}
              <TransitionCharts backendResults={sourceResults} plotTheme={plotTheme} copy={copy} />
              <AngleVsStateCharts backendResults={sourceResults} plotTheme={plotTheme} copy={copy} />
              <SessionSummaryCharts backendResults={sourceResults} plotTheme={plotTheme} copy={copy} />
            </div>
          </Tabs.Content>
          <Tabs.Content
            className="insights-tab-content"
            value="model"
            forceMount
            inert={tab !== 'model'}
            aria-hidden={tab !== 'model'}
          >
            <div className="insights-grid">
              <ModelMetricsPanel plotTheme={plotTheme} copy={copy} />
            </div>
          </Tabs.Content>
        </div>
      </Tabs.Root>
    </section>
  )
}
