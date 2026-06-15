import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import * as Tabs from '@radix-ui/react-tabs'
import { Download, FileDown, TriangleAlert, Info, MapPin } from 'lucide-react'
import clsx from 'clsx'
import { AngleVsStateCharts } from '../components/insights/AngleVsStateCharts'
import { TransitionCharts } from '../components/insights/TransitionCharts'
import { SessionSummaryCharts } from '../components/insights/SessionSummaryCharts'
import { InferencePerformance } from '../components/insights/InferencePerformance'
import { InsightsSummaryStrip } from '../components/insights/InsightsSummaryStrip'
import { sessionRunwaySummary } from '../lib/runwaySelection'
import {
  confidenceValues,
  stableTransitionEvents,
  summarizeSession,
  transitionCsv,
} from '../lib/insightsTransforms'
import { fetchLogDetail } from '../lib/api'
import { localizedErrorMessage } from '../lib/errorMessages'
import { formatTimestamp } from '../lib/format'
import { useChartExport } from '../hooks/useChartExport'
import { useFetch } from '../hooks/useFetch'
import { useLiveDemo } from '../context/liveDemoContext'

// Insights is an overview-first analytical console: an always-visible session
// snapshot (the verdict layer) above four focused, question-led section tabs —
//   • Transition analysis   (commissioning: measured crossing angles + flips)
//   • Angle analysis         (redness vs angle small multiples + descent profile)
//   • Lamp analysis          (per-light state mix + detection confidence)
//   • Inference performance  (filterable fleet distribution + latency percentiles)
// Model evaluation metrics (precision/recall/mAP + per-class P/R/F1) live on the
// Models page now — Insights stays focused on the SESSION, not the detector's CV
// scores. Progressive disclosure: the user sees one focused section at a time and
// the most relevant one is selected by default. All panels are force-mounted (CSS
// parks the inactive ones off-screen at full size) so PDF export captures every
// chart and Plotly never re-initialises on a tab switch.
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

  // `tab === null` means "not chosen yet" — the active tab then tracks the most
  // relevant section for the loaded data (which can arrive async in history mode);
  // the first manual pick pins it. Derived, so no set-state-in-effect.
  const [tab, setTab] = useState(null)
  const sourceMode = logId ? 'history' : 'live'
  const sourceResults = useMemo(
    () => (sourceMode === 'history' ? (historyLog.data ? [historyLog.data] : []) : (backendResults ?? [])),
    [sourceMode, historyLog.data, backendResults],
  )
  const hasSession = (sourceResults?.length ?? 0) > 0
  const transitionEvents = useMemo(
    () => stableTransitionEvents(sourceResults).filter(
      (event) => Number.isInteger(event?.lamp_index) && event.lamp_index >= 1 && event.lamp_index <= 4,
    ),
    [sourceResults],
  )
  const hasTransitions = transitionEvents.length > 0

  // At-a-glance roll-up for the overview strip (lamps crossed / elevation / trust)
  // plus the extra KPIs the strip surfaces (transitions, detection confidence, detector).
  const summary = useMemo(() => summarizeSession(sourceResults), [sourceResults])
  const summaryExtra = useMemo(() => {
    const confidences = confidenceValues(sourceResults)
    const avgConfidence = confidences.length
      ? Math.round(confidences.reduce((total, value) => total + value, 0) / confidences.length)
      : null
    const first = sourceResults?.[0]
    return {
      transitionsCount: transitionEvents.length,
      avgConfidence,
      detectorLabel: first?.model_label || first?.model_id || null,
    }
  }, [sourceResults, transitionEvents])

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

  // Section tabs in priority order. The fleet/model sections always have data
  // (their own backend fetches); the session sections show honest empty states
  // until an analysis is run.
  const tabDefs = [
    { value: 'transition', label: copy.insights.tabTransition, question: copy.insights.qTransition },
    { value: 'angle', label: copy.insights.tabAngle, question: copy.insights.qAngle },
    { value: 'lamp', label: copy.insights.tabLamp, question: copy.insights.qLamp },
    { value: 'inference', label: copy.insights.tabInference, question: copy.insights.qInference },
  ]
  // Most relevant section first: a swept video leads with transitions, any other
  // analysis with lamp states, and a no-session visit with the fleet inference
  // section (the only tab that always has its own backend data).
  const preferredTab = hasTransitions ? 'transition' : hasSession ? 'lamp' : 'inference'
  const activeTab = tab ?? preferredTab

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

  // Each tab panel is force-mounted (inactive ones parked off-screen by CSS) so the
  // PDF export still captures every chart node. The question subhead states what the
  // section answers; the grid hosts the section's existing chart components.
  const renderPanel = (def, children) => (
    <Tabs.Content
      key={def.value}
      className="insights-tab-content"
      value={def.value}
      forceMount
      inert={activeTab !== def.value}
      aria-hidden={activeTab !== def.value}
    >
      <p className="section-question">{def.question}</p>
      <div className="insights-grid">{children}</div>
    </Tabs.Content>
  )

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
          them with empty session cards (the model/inference tabs still have data). */}
      {!hasSession && !(sourceMode === 'history' && historyLog.loading) && !historyLog.error && (
        <div className="insights-cta" role="note">
          <Info size={18} aria-hidden="true" />
          <span>{copy.insights.emptyCta}</span>
          <Link className="text-link" to="/live-demo">
            {copy.insights.emptyCtaLink}
          </Link>
        </div>
      )}

      {/* Overview layer: stated before the tabs and OUTSIDE them (so it isn't parked
          off-screen with an inactive force-mounted panel). Self-hides when empty. */}
      <InsightsSummaryStrip
        summary={summary}
        sourceMeta={{ label: sourceLabel, timestamp: sourceTimestamp }}
        extra={summaryExtra}
        copy={copy}
      />

      <Tabs.Root value={activeTab} onValueChange={setTab} className="insights-tabs">
        <Tabs.List className="insights-tab-list" aria-label={copy.insights.eyebrow}>
          {tabDefs.map((def) => (
            <Tabs.Trigger key={def.value} className="insights-tab-trigger" value={def.value}>
              {def.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        <div className="insights-tab-viewport" ref={insightsRef}>
          {renderPanel(
            tabDefs[0],
            <TransitionCharts backendResults={sourceResults} plotTheme={plotTheme} copy={copy} />,
          )}
          {renderPanel(
            tabDefs[1],
            <AngleVsStateCharts backendResults={sourceResults} plotTheme={plotTheme} copy={copy} />,
          )}
          {renderPanel(
            tabDefs[2],
            <SessionSummaryCharts backendResults={sourceResults} plotTheme={plotTheme} copy={copy} />,
          )}
          {renderPanel(tabDefs[3], <InferencePerformance plotTheme={plotTheme} copy={copy} />)}
        </div>
      </Tabs.Root>
    </section>
  )
}
