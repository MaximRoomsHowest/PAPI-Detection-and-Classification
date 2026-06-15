import { percent } from '../../lib/format'
import { globalStateLabel } from '../../lib/stateLabels'
import { StateDistributionBar } from './StateDistributionBar'

// A stats-card heading, with a "filtered" chip when the aggregates describe the
// active filter selection rather than the whole table — without it a user who
// filters to 9 rows still reads "Recent analyses 29" and assumes a bug.
function ScopedLabel({ label, isFiltered, copy }) {
  return (
    <span>
      {label}
      {isFiltered && <em className="history-summary__scope">{copy.history.filteredScope}</em>}
    </span>
  )
}

// Processing-time values carry their unit (ms) to match the Insights latency
// labelling; the em-dash stands in for an absent/empty value with no stray unit.
function ms(value) {
  return Number.isFinite(value) ? `${value} ms` : '—'
}

// Summary strip for the History page. Reshaped to lead with what the log is ABOUT
// — the spread of glide-path states across the (optionally filtered) analyses —
// followed by the sample counts, average confidence, and processing percentiles.
// The serving-model filename / training-run / checksum / val-accuracy that used to
// head this strip are model provenance, not log analytics, and now live on the
// Models page. Presentational: all data comes from the parent's /api/stats fetch.
export function HistoryStats({ stats, isFiltered = false, copy }) {
  const stateCounts = stats?.by_global_state ?? {}
  const states = Object.entries(stateCounts)
    .filter(([, n]) => Number.isFinite(n) && n > 0)
    .sort((a, b) => b[1] - a[1])

  return (
    <div className="history-summary-grid">
      {states.length > 0 && (
        <div className="history-summary history-summary--wide">
          <ScopedLabel label={copy.history.stateMix} isFiltered={isFiltered} copy={copy} />
          <StateDistributionBar counts={stateCounts} copy={copy} className="history-summary__dist" />
          <ul className="history-state-legend">
            {states.map(([state, count]) => (
              <li key={state}>
                <span className={`history-state-legend__swatch state-seg-${state}`} aria-hidden="true" />
                {globalStateLabel(state, copy)}
                <span className="history-state-legend__count tnum">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="history-summary">
        <ScopedLabel label={copy.history.sample} isFiltered={isFiltered} copy={copy} />
        <strong className="tnum">{stats?.total_analyses ?? stats?.sample_size ?? 0}</strong>
        <small className="tnum">
          {stats
            ? `${stats.image_count} ${copy.history.mediaImage} · ${stats.video_count} ${copy.history.mediaVideo}`
            : copy.history.unavailable}
        </small>
      </div>
      <div className="history-summary">
        <ScopedLabel label={copy.history.confidenceAvg} isFiltered={isFiltered} copy={copy} />
        <strong className="tnum">{stats?.avg_confidence != null ? `${percent(stats.avg_confidence)}%` : '—'}</strong>
        <small>{copy.history.stats}</small>
      </div>
      <div className="history-summary">
        <ScopedLabel label={copy.history.avg} isFiltered={isFiltered} copy={copy} />
        <strong className="tnum">{ms(stats?.avg_processing_ms)}</strong>
        <small className="tnum">
          {`${copy.history.p50} ${ms(stats?.p50_processing_ms)} · ${copy.history.p95} ${ms(stats?.p95_processing_ms)}`}
        </small>
      </div>
    </div>
  )
}
