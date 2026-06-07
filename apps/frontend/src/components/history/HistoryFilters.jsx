import { Download, X } from 'lucide-react'

// Runway/state filter selects, the clear-filters reset, and the CSV export button.
// Presentational: the parent owns the filter state + the (pre-bound) change handlers
// and the busy flags. `onRunwayChange` / `onStateChange` are ready-to-use <select>
// onChange handlers so the setters never have to leak down here.
export function HistoryFilters({
  runwayFilter,
  stateFilter,
  runwayOptions,
  stateOptions,
  hasActiveFilters,
  onRunwayChange,
  onStateChange,
  onClearFilters,
  onExportCsv,
  isExporting,
  isBusy,
  total,
  copy,
}) {
  return (
    <div className="history-controls">
      <select
        className="history-filter"
        value={runwayFilter}
        onChange={onRunwayChange}
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
        onChange={onStateChange}
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
          onClick={onClearFilters}
        >
          <X size={16} />
          {copy.history.clearFilters}
        </button>
      )}
      <button
        className="secondary-button"
        type="button"
        onClick={onExportCsv}
        disabled={isExporting || isBusy || total === 0}
      >
        <Download size={18} />
        {isExporting ? copy.history.exporting : copy.history.exportCsv}
      </button>
    </div>
  )
}
