import { percent } from '../../lib/format'

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

// Summary cards: serving model + provenance, optional val accuracy, sample counts,
// avg confidence, and processing-time percentiles. Presentational — all data comes
// from props (the HistoryPage parent owns the fetches). The model/accuracy cards
// describe the serving model and never carry the filtered-scope chip.
export function HistoryStats({ modelInfo, stats, isFiltered = false, copy }) {
  return (
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
        <strong className="tnum">{stats?.avg_processing_ms ?? '—'}</strong>
        <small className="tnum">
          {`${copy.history.p50} ${stats?.p50_processing_ms ?? '—'} · ${copy.history.p95} ${stats?.p95_processing_ms ?? '—'}`}
        </small>
      </div>
    </div>
  )
}
