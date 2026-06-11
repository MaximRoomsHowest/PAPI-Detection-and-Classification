import { useState } from 'react'
import { Cpu, Target } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { InlineMetric } from '../InlineMetric'
import { useFetch } from '../../hooks/useFetch'
import { fetchModelInfo, fetchModels, fetchStats } from '../../lib/api'
import {
  axisTitle,
  basePlotLayout,
  baseAxisStyle,
  plotlyConfig,
  CHART_HEIGHT,
  integerTicks,
  barValueLabels,
} from '../../catalog/plotly'
import { backendStateId, stateCatalog } from '../../catalog/stateCatalog'
import { translateState } from '../../i18n/translate'
import { percent } from '../../lib/format'

// Aggregate model/dataset panel. All values come from the backend:
//   /api/stats  -> logged global-state distribution + throughput
//   /api/model  -> validation-split detection metrics (box, NOT per-class)
// Per-class precision/recall/F1 and a confusion matrix are intentionally NOT
// shown: the backend exposes only box-detection metrics, so building them would
// be fabrication (documented blocker).

function stateLabel(rawState, copy) {
  const id = backendStateId[rawState] ?? 'unknown'
  const entry = stateCatalog.find((state) => state.id === id)
  return entry ? translateState(entry, copy).label : rawState
}

function ChartSkeleton({ copy }) {
  return (
    <div className="chart-skeleton" role="status">
      {copy.insights.stateLoading}
    </div>
  )
}

function GlobalStateDistribution({ stats, plotTheme, copy }) {
  const entries = Object.entries(stats?.by_global_state ?? {})
  if (!entries.length) {
    return (
      <AngleEmptyState
        icon={<Target size={26} aria-hidden="true" />}
        message={copy.insights.noSessionData}
      />
    )
  }
  const labels = entries.map(([state]) => stateLabel(state, copy))
  const values = entries.map(([, count]) => count)
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      copy={copy}
      ariaLabel={copy.insights.statsTitle}
      data={[
        {
          type: 'bar',
          x: labels,
          y: values,
          marker: { color: plotTheme.accent },
          // Print each bar's value so the static PDF export isn't label-less (audit).
          ...barValueLabels(values, plotTheme),
          hovertemplate: `%{x}<br>${copy.insights.statsAxis}: %{y}<extra></extra>`,
        },
      ]}
      layout={basePlotLayout(plotTheme, {
        height: CHART_HEIGHT,
        margin: { l: 46, r: 14, t: 10, b: 70 },
        xaxis: baseAxisStyle(plotTheme, {
          tickangle: -25,
          tickfont: { color: plotTheme.muted, size: 11 },
        }),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.statsAxis, plotTheme),
          gridcolor: plotTheme.grid,
          // Aggregates across EVERY logged analysis (can be thousands), so a fixed
          // `dtick:1` produced an unreadable wall of labels (audit B8).
          ...integerTicks(Math.max(0, ...values)),
          rangemode: 'tozero',
        }),
      })}
      useResizeHandler
    />
  )
}

function ModelMetrics({ model, copy }) {
  const metrics = model?.val_metrics
  if (!metrics) {
    return (
      <AngleEmptyState
        icon={<Cpu size={26} aria-hidden="true" />}
        message={copy.insights.loadError}
      />
    )
  }
  const fmt = (value) => (Number.isFinite(value) ? value.toFixed(3) : '—')
  return (
    <>
      <div className="metric-grid">
        <InlineMetric label={copy.insights.metricPrecision} value={fmt(metrics.precision)} />
        <InlineMetric label={copy.insights.metricRecall} value={fmt(metrics.recall)} />
        <InlineMetric label={copy.insights.metricMap50} value={fmt(metrics.map50)} />
        <InlineMetric label={copy.insights.metricMap5095} value={fmt(metrics.map50_95)} />
        {/* The operating confidence threshold — surfaced so the "unknown" verdict
            on a faint lamp reads as a deliberate, tunable gate rather than a miss. */}
        <InlineMetric
          label={copy.insights.metricThreshold}
          value={Number.isFinite(model.confidence_threshold) ? Math.round(model.confidence_threshold * 100) : '—'}
          suffix={Number.isFinite(model.confidence_threshold) ? '%' : ''}
        />
      </div>
      {/* The card subtitle already carries the "box detection, not per-class"
          disclaimer; here we surface only the backend's own val_metrics note. */}
      {metrics.note ? <p className="viz-footnote">{metrics.note}</p> : null}
    </>
  )
}

export function ModelMetricsPanel({ plotTheme, copy }) {
  const stats = useFetch(fetchStats, [])
  // Every registry model's card is inspectable, not only the backend default —
  // /api/model?model_id always supported this; the UI never sent an id
  // (integration audit 2026-06-11). null = the backend default's card.
  const [selectedId, setSelectedId] = useState(null)
  const models = useFetch(fetchModels, [])
  const model = useFetch(() => fetchModelInfo(selectedId ?? undefined), [selectedId], {
    keepPreviousData: true,
  })
  const pickerOptions = Array.isArray(models.data) ? models.data : []

  return (
    <>
      <article className="viz-card">
        <div className="viz-heading">
          <Target size={18} />
          <div>
            <h3>{copy.insights.statsTitle}</h3>
            <p>{copy.insights.statsText}</p>
          </div>
        </div>
        {stats.loading ? (
          <ChartSkeleton copy={copy} />
        ) : stats.error ? (
          <AngleEmptyState icon={<Target size={26} aria-hidden="true" />} message={copy.insights.loadError} />
        ) : (
          <GlobalStateDistribution stats={stats.data} plotTheme={plotTheme} copy={copy} />
        )}
        {stats.data ? (
          <div className="metric-grid metric-grid--compact stats-metrics">
            <InlineMetric label={copy.insights.statsSamples} value={stats.data.total_analyses ?? 0} />
            <InlineMetric
              label={copy.insights.statsAvgConfidence}
              value={stats.data.avg_confidence != null ? percent(stats.data.avg_confidence) : '—'}
              suffix={stats.data.avg_confidence != null ? '%' : ''}
            />
            <InlineMetric
              label={copy.insights.statsThroughput}
              value={stats.data.avg_processing_ms != null ? Math.round(stats.data.avg_processing_ms) : '—'}
              suffix={stats.data.avg_processing_ms != null ? ' ms' : ''}
            />
          </div>
        ) : null}
      </article>

      <article className="viz-card">
        <div className="viz-heading">
          <Cpu size={18} />
          <div>
            <h3>{copy.insights.modelMetricsTitle}</h3>
            <p>{copy.insights.modelMetricsText}</p>
          </div>
        </div>
        {pickerOptions.length > 1 && (
          <div className="model-selector" role="group" aria-label={copy.insights.modelPicker}>
            <span className="model-selector__label">{copy.insights.modelPicker}</span>
            <div className="model-selector__options">
              {pickerOptions.map((option) => {
                const active =
                  selectedId === option.model_id || (selectedId === null && option.is_default)
                return (
                  <button
                    key={option.model_id}
                    type="button"
                    className={`model-selector__option${active ? ' is-active' : ''}`}
                    aria-pressed={active}
                    // Unavailable entries stay selectable ON PURPOSE: their card
                    // (provenance + val_metrics) comes from the registry, not the
                    // weights file — exactly what a reviewer wants to inspect.
                    title={option.description || option.model_role || undefined}
                    onClick={() => setSelectedId(option.model_id)}
                  >
                    {option.model_label || option.model_id}
                  </button>
                )
              })}
            </div>
          </div>
        )}
        {model.loading && !model.data ? (
          <ChartSkeleton copy={copy} />
        ) : model.error ? (
          <AngleEmptyState icon={<Cpu size={26} aria-hidden="true" />} message={copy.insights.loadError} />
        ) : (
          <>
            {model.data && (
              <p className="viz-footnote">
                {`${model.data.model_label || model.data.model_id || ''}`}
                {model.data.training_run ? ` · ${copy.history.trainingRun}: ${model.data.training_run}` : ''}
                {model.data.dataset_split_evaluated ? ` · ${model.data.dataset_split_evaluated} split` : ''}
              </p>
            )}
            <ModelMetrics model={model.data} copy={copy} />
          </>
        )}
      </article>
    </>
  )
}
