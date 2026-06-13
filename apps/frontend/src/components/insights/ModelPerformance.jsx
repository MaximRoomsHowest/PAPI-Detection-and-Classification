import { useState } from 'react'
import { Cpu } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { InlineMetric } from '../InlineMetric'
import { useFetch } from '../../hooks/useFetch'
import { fetchModelInfo, fetchModels } from '../../lib/api'
import {
  axisTitle,
  basePlotLayout,
  baseAxisStyle,
  plotlyConfig,
} from '../../catalog/plotly'
import { lampStateLabel } from '../../lib/stateLabels'

// "Model performance" section: the selected registry entry's evaluation card —
// box-detection metrics (precision / recall / mAP), and, when the card carries
// real measured per-class numbers (the 3-class transition entry does), a grouped
// bar of per-class precision/recall/F1 with the exact values kept in the table
// beneath it. Every value is verbatim from /api/model.val_metrics — deriving any
// missing one would be fabrication (documented blocker), so absent stays absent.
//
// Note on the confusion matrix the brief asks for: the model card exposes
// precision/recall/F1/mAP only — there are no per-class confusion COUNTS in the
// API, so a matrix cannot be drawn without inventing data. The per-class bar is
// the honest visual the available numbers support.

const fmt = (value) => (Number.isFinite(value) ? value.toFixed(3) : '—')

// Cool, CVD-distinct metric tones, deliberately outside the lamp-identity and
// reserved red/white/amber state palettes (and never purple) so a metric bar is
// never read as a lamp or a state.
const METRIC_SERIES = (plotTheme, copy) => [
  { key: 'precision', name: copy.insights.metricPrecision, color: '#4f8fd0' },
  { key: 'recall', name: copy.insights.metricRecall, color: '#2fa98f' },
  { key: 'f1', name: copy.insights.metricF1, color: plotTheme.accent },
]

function ChartSkeleton({ copy }) {
  return (
    <div className="chart-skeleton" role="status">
      {copy.insights.stateLoading}
    </div>
  )
}

function PerClassMetricsChart({ perClass, plotTheme, copy }) {
  const classes = perClass
  const x = classes.map(([className]) => lampStateLabel(className, copy))
  const series = METRIC_SERIES(plotTheme, copy)
  const data = series.map((metric) => ({
    type: 'bar',
    name: metric.name,
    x,
    y: classes.map(([, row]) => (Number.isFinite(row?.[metric.key]) ? row[metric.key] : null)),
    marker: { color: metric.color, line: { color: plotTheme.paper, width: 1 } },
    // Print each value so the static PDF export keeps the numbers (no hover there).
    text: classes.map(([, row]) => (Number.isFinite(row?.[metric.key]) ? row[metric.key].toFixed(2) : '')),
    textposition: 'outside',
    textfont: { color: plotTheme.muted, size: 10 },
    cliponaxis: false,
    hovertemplate: `%{x}<br>${metric.name}: %{y:.3f}<extra></extra>`,
  }))
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      copy={copy}
      ariaLabel={copy.insights.perClassChartTitle}
      data={data}
      layout={basePlotLayout(plotTheme, {
        height: 300,
        barmode: 'group',
        bargap: 0.28,
        bargroupgap: 0.08,
        margin: { l: 46, r: 14, t: 12, b: 40 },
        legend: { orientation: 'h', y: -0.18, font: { color: plotTheme.muted, size: 11 } },
        xaxis: baseAxisStyle(plotTheme),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.metricScoreAxis, plotTheme),
          range: [0, 1.08],
          dtick: 0.25,
          gridcolor: plotTheme.grid,
        }),
        showlegend: true,
      })}
      useResizeHandler
    />
  )
}

function ModelMetrics({ model, plotTheme, copy }) {
  const metrics = model?.val_metrics
  if (!metrics) {
    return (
      <AngleEmptyState
        icon={<Cpu size={26} aria-hidden="true" />}
        message={copy.insights.loadError}
      />
    )
  }
  const perClass = metrics.per_class && Object.entries(metrics.per_class)
  return (
    <>
      <div className="metric-grid">
        <InlineMetric label={copy.insights.metricPrecision} value={fmt(metrics.precision)} />
        <InlineMetric label={copy.insights.metricRecall} value={fmt(metrics.recall)} />
        <InlineMetric label={copy.insights.metricMap50} value={fmt(metrics.map50)} />
        <InlineMetric label={copy.insights.metricMap5095} value={fmt(metrics.map50_95)} />
        <InlineMetric
          label={copy.insights.metricThreshold}
          value={Number.isFinite(model.confidence_threshold) ? Math.round(model.confidence_threshold * 100) : '—'}
          suffix={Number.isFinite(model.confidence_threshold) ? '%' : ''}
        />
      </div>

      {/* MEASURED per-class precision/recall/F1 as a grouped bar (visual), with the
          exact values kept in the table below as the accessible companion. */}
      {perClass?.length > 0 ? (
        <>
          <div className="per-class-chart">
            <h4>{copy.insights.perClassChartTitle}</h4>
            <p className="viz-subhead">{copy.insights.perClassChartText}</p>
            <PerClassMetricsChart perClass={perClass} plotTheme={plotTheme} copy={copy} />
          </div>
          <table className="model-per-class">
            <caption>{copy.insights.metricPerClass}</caption>
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col">{copy.insights.metricPrecision}</th>
                <th scope="col">{copy.insights.metricRecall}</th>
                <th scope="col">{copy.insights.metricF1}</th>
                <th scope="col">{copy.insights.metricMap50}</th>
              </tr>
            </thead>
            <tbody>
              {perClass.map(([className, row]) => (
                <tr key={className}>
                  <th scope="row">{lampStateLabel(className, copy)}</th>
                  <td className="tnum">{fmt(row?.precision)}</td>
                  <td className="tnum">{fmt(row?.recall)}</td>
                  <td className="tnum">{fmt(row?.f1)}</td>
                  <td className="tnum">{fmt(row?.map50)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
      {perClass?.length > 0 && metrics.note ? <p className="viz-footnote">{metrics.note}</p> : null}
      {!perClass?.length ? <p className="viz-footnote">{copy.insights.metricNoPerClass}</p> : null}
    </>
  )
}

function ModelCredentials({ model, copy }) {
  if (!model) return null
  const role = model.model_role ? (copy.live.modelRole?.[model.model_role] ?? model.model_role) : '—'
  const split = model.dataset_split_evaluated ? `${model.dataset_split_evaluated} split` : '—'
  const threshold = Number.isFinite(model.confidence_threshold)
    ? `${Math.round(model.confidence_threshold * 100)}%`
    : '—'
  return (
    <div className="model-credentials" aria-label={copy.insights.modelCredentials}>
      <InlineMetric label={copy.insights.modelRole} value={role} />
      <InlineMetric label={copy.history.trainingRun} value={model.training_run || '—'} />
      <InlineMetric label={copy.insights.modelSplit} value={split} />
      <InlineMetric label={copy.insights.metricThreshold} value={threshold} />
    </div>
  )
}

export function ModelPerformance({ plotTheme, copy }) {
  // Every registry model's card is inspectable, not only the backend default —
  // /api/model?model_id always supported this (integration audit 2026-06-11).
  // null = the backend default's card.
  const [selectedId, setSelectedId] = useState(null)
  const models = useFetch(fetchModels, [])
  const model = useFetch(() => fetchModelInfo(selectedId ?? undefined), [selectedId], {
    keepPreviousData: true,
  })
  const pickerOptions = Array.isArray(models.data) ? models.data : []

  return (
    <article className="viz-card span-all">
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
              const active = selectedId === option.model_id || (selectedId === null && option.is_default)
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
          {model.data && <ModelCredentials model={model.data} copy={copy} />}
          <ModelMetrics model={model.data} plotTheme={plotTheme} copy={copy} />
        </>
      )}
    </article>
  )
}
