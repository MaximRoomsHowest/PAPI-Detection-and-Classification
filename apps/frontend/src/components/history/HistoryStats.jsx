import { percent } from '../../lib/format'

// Summary cards: serving model + provenance, optional val accuracy, sample counts,
// avg confidence, and processing-time percentiles. Presentational — all data comes
// from props (the HistoryPage parent owns the fetches).
export function HistoryStats({ modelInfo, stats, copy }) {
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
  )
}
