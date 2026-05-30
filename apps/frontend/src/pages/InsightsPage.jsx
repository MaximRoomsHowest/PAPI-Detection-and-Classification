import { useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { Download, TriangleAlert } from 'lucide-react'
import clsx from 'clsx'
import { AngleVsStateCharts } from '../components/insights/AngleVsStateCharts'
import { TransitionCharts } from '../components/insights/TransitionCharts'
import { SessionSummaryCharts } from '../components/insights/SessionSummaryCharts'
import { ModelMetricsPanel } from '../components/insights/ModelMetricsPanel'

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
  copy,
}) {
  // Controlled so the off-screen, force-mounted panel can be marked `inert`
  // (removed from the tab order and the a11y tree) while staying in the DOM at
  // full size for PDF export. Plotly.toImage still reads inert nodes.
  const [tab, setTab] = useState('current')
  return (
    <section className="insights-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.insights.eyebrow}</p>
          <h2>{copy.insights.title}</h2>
        </div>
        <div className="section-actions">
          <button
            className={clsx('secondary-button', exportError && 'has-error')}
            type="button"
            onClick={onDownloadCharts}
            disabled={isExporting}
          >
            <Download size={18} />
            {isExporting ? copy.insights.preparing : copy.insights.download}
          </button>
          <span className="source-note">{copy.insights.source}</span>
        </div>
      </div>

      {exportError && (
        <div className="export-status error" role="alert" aria-live="assertive">
          <TriangleAlert size={16} />
          {exportError}
        </div>
      )}

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
