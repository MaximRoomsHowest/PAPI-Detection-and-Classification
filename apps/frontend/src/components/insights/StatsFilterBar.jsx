import { Filter, X } from 'lucide-react'

// Server-side filter controls for the fleet-level inference statistics. Every
// value maps 1:1 onto a /api/stats query parameter (the same camelCase set
// fetchStats/fetchLogs accept), so the section's distribution, throughput, and
// latency all reflect the chosen slice without any client-side recomputation.
//
// Presentational + controlled: the parent owns the `value` object and re-fetches
// when it changes. Mirrors the History page's filter formats exactly so the
// backend contract is shared (min_confidence is a 0-1 float bucket; created_after
// is a YYYY-MM-DD date; media_type is image|video).
const CONFIDENCE_STEPS = ['0.5', '0.75', '0.9']

const EMPTY = { mediaType: '', modelId: '', createdAfter: '', minConfidence: '' }

export function StatsFilterBar({ value, onChange, models, count, copy }) {
  const filters = { ...EMPTY, ...value }
  const modelOptions = Array.isArray(models) ? models : []
  const hasActiveFilters = Object.values(filters).some((entry) => entry !== '' && entry != null)

  const set = (key) => (event) => onChange({ ...filters, [key]: event.target.value })

  return (
    <div className="stats-filter-bar" role="group" aria-label={copy.insights.filtersTitle}>
      <span className="stats-filter-bar__title">
        <Filter size={15} aria-hidden="true" />
        {copy.insights.filtersTitle}
      </span>

      <label className="stats-filter">
        <span>{copy.insights.filterMediaLabel}</span>
        <select value={filters.mediaType} onChange={set('mediaType')} aria-label={copy.insights.filterMediaLabel}>
          <option value="">{copy.insights.filterMediaAll}</option>
          <option value="image">{copy.insights.filterMediaImage}</option>
          <option value="video">{copy.insights.filterMediaVideo}</option>
        </select>
      </label>

      <label className="stats-filter">
        <span>{copy.insights.filterModelLabel}</span>
        <select value={filters.modelId} onChange={set('modelId')} aria-label={copy.insights.filterModelLabel}>
          <option value="">{copy.insights.filterModelAll}</option>
          {modelOptions.map((option) => (
            <option key={option.model_id} value={option.model_id}>
              {option.model_label || option.model_id}
            </option>
          ))}
        </select>
      </label>

      <label className="stats-filter">
        <span>{copy.insights.filterMinConfidence}</span>
        <select
          value={filters.minConfidence}
          onChange={set('minConfidence')}
          aria-label={copy.insights.filterMinConfidence}
        >
          <option value="">—</option>
          {CONFIDENCE_STEPS.map((step) => (
            <option key={step} value={step}>
              ≥ {Math.round(Number(step) * 100)}%
            </option>
          ))}
        </select>
      </label>

      <label className="stats-filter">
        <span>{copy.insights.filterDateFrom}</span>
        <input
          type="date"
          value={filters.createdAfter}
          onChange={set('createdAfter')}
          aria-label={copy.insights.filterDateFrom}
        />
      </label>

      {hasActiveFilters && (
        <button type="button" className="ghost-button stats-filter-bar__reset" onClick={() => onChange({ ...EMPTY })}>
          <X size={15} aria-hidden="true" />
          {copy.insights.filterReset}
        </button>
      )}

      {Number.isFinite(count) && (
        <span className="stats-filter-bar__count mono" aria-live="polite">
          {copy.insights.filterShowing.replace('{n}', count)}
        </span>
      )}
    </div>
  )
}
