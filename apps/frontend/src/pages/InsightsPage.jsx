import { Download, TriangleAlert } from 'lucide-react'
import clsx from 'clsx'
import { GlobalStateDecoder } from '../components/insights/GlobalStateDecoder'
import { TransitionRibbon } from '../components/insights/TransitionRibbon'

export function InsightsPage({
  activeScenario,
  plotTheme,
  insightsRef,
  isExporting,
  exportError,
  onDownloadCharts,
  copy,
}) {
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

      {/* PDF export feedback (audit F06/F07): surface failures + the
          no-charts case to the user via an aria-live banner instead of only
          logging to the console. */}
      {exportError && (
        <div className="export-status error" role="alert" aria-live="assertive">
          <TriangleAlert size={16} />
          {exportError}
        </div>
      )}

      <div className="insight-grid" ref={insightsRef}>
        <GlobalStateDecoder scenario={activeScenario} plotTheme={plotTheme} copy={copy} />
        <TransitionRibbon activeScenario={activeScenario} plotTheme={plotTheme} copy={copy} />
      </div>
    </section>
  )
}
