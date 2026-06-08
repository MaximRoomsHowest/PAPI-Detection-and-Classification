import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import * as Tabs from '@radix-ui/react-tabs'
import { Download, TriangleAlert, Info, MapPin } from 'lucide-react'
import clsx from 'clsx'
import { AngleVsStateCharts } from '../components/insights/AngleVsStateCharts'
import { TransitionCharts } from '../components/insights/TransitionCharts'
import { SessionSummaryCharts } from '../components/insights/SessionSummaryCharts'
import { ModelMetricsPanel } from '../components/insights/ModelMetricsPanel'
import { InsightsSummaryStrip } from '../components/insights/InsightsSummaryStrip'
import { sessionRunwaySummary } from '../lib/runwaySelection'
import { summarizeSession } from '../lib/insightsTransforms'

// Insights is split into two tabs: "Current analysis" (charts built from the
// session's real results — angle-vs-state, transitions, per-light/confidence
// distributions) and "Model & dataset" (aggregate /api/stats + /api/model).
// Both tab panels are force-mounted (CSS parks the inactive one off-screen at
// full size) so PDF export captures every chart and Plotly never re-initialises
// on tab switch.
export function InsightsPage({
  backendResults,
  plotTheme,
  insightsRef,
  isExporting,
  exportError,
  onDownloadCharts,
  runways = [],
  copy,
}) {
  // Controlled so the off-screen, force-mounted panel can be marked `inert`
  // (removed from the tab order and the a11y tree) while staying in the DOM at
  // full size for PDF export. Plotly.toImage still reads inert nodes.
  const [tab, setTab] = useState('current')
  // "Current analysis" charts the in-memory results of THIS session only (audit C1).
  const hasSession = (backendResults?.length ?? 0) > 0
  // At-a-glance roll-up for the verdict strip (lamps crossed / elevation / trust).
  const summary = useMemo(() => summarizeSession(backendResults), [backendResults])
  const runwaySummary = sessionRunwaySummary(backendResults, runways)
  const runwayContextText =
    runwaySummary.kind === 'mixed'
      ? copy.insights.runwayContextMixed.replace('{runways}', runwaySummary.label)
      : runwaySummary.kind === 'single'
        ? copy.insights.runwayContext.replace('{runway}', runwaySummary.label)
        : copy.insights.runwayContextNone
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
          <span className="source-note">{copy.insights.scopeNote}</span>
        </div>
      </div>

      {exportError && (
        <div className="export-status error" role="alert" aria-live="assertive">
          <TriangleAlert size={16} />
          {exportError}
        </div>
      )}

      {/* No analysis this session: point the user at Live Demo instead of leaving
          them with several empty cards and a working-but-lonely model chart (audit D5). */}
      {!hasSession && (
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
      <InsightsSummaryStrip summary={summary} copy={copy} />

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
          >
            <div className="insights-grid">
              <AngleVsStateCharts backendResults={backendResults} plotTheme={plotTheme} copy={copy} />
              <TransitionCharts backendResults={backendResults} plotTheme={plotTheme} copy={copy} />
              <SessionSummaryCharts backendResults={backendResults} plotTheme={plotTheme} copy={copy} />
            </div>
          </Tabs.Content>
          <Tabs.Content
            className="insights-tab-content"
            value="model"
            forceMount
            inert={tab !== 'model'}
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
