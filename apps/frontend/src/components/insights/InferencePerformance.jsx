import { useState } from 'react'
import { Activity, Gauge, Target } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import { InlineMetric } from '../InlineMetric'
import { StatsFilterBar } from './StatsFilterBar'
import { useFetch } from '../../hooks/useFetch'
import { fetchModels, fetchStats } from '../../lib/api'
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

// "Inference performance" section: the fleet view from /api/stats — the logged
// global-state distribution, throughput, and processing-time percentiles, all
// re-fetched server-side as the filter bar changes the queried slice.
//
// Honesty note: /api/stats exposes avg / P50 / P95 processing time, NOT a raw
// per-analysis latency array — so the timing chart shows those three percentile
// statistics (clearly labelled), never a fabricated distribution histogram.

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
    return <AngleEmptyState icon={<Target size={26} aria-hidden="true" />} message={copy.insights.noSessionData} />
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
          ...barValueLabels(values, plotTheme),
          hovertemplate: `%{x}<br>${copy.insights.statsAxis}: %{y}<extra></extra>`,
        },
      ]}
      layout={basePlotLayout(plotTheme, {
        height: CHART_HEIGHT,
        margin: { l: 46, r: 14, t: 10, b: 70 },
        xaxis: baseAxisStyle(plotTheme, { tickangle: -25, tickfont: { color: plotTheme.muted, size: 11 } }),
        yaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.statsAxis, plotTheme),
          gridcolor: plotTheme.grid,
          ...integerTicks(Math.max(0, ...values)),
          rangemode: 'tozero',
        }),
      })}
      useResizeHandler
    />
  )
}

// Cool, non-reserved tones (never red/white/amber, never purple) so the latency
// bars never read as a lamp state. Image vs video get distinct hues.
const LATENCY_COLORS = { image: '#2f6fed', video: '#0f9d8c' }

function _round(value) {
  return Number.isFinite(value) ? Math.round(value) : null
}

function LatencyChart({ stats, plotTheme, copy }) {
  // Mean / Median (P50) / Tail (P95), split by media type — a whole-video analysis
  // spans many frames so its processing time dwarfs a single image's; mixing them
  // into one bar would be misleading.
  const labels = [copy.insights.latencyAvg, copy.insights.latencyP50, copy.insights.latencyP95]
  const imageVals = [_round(stats?.image_avg_processing_ms), stats?.image_p50_processing_ms ?? null, stats?.image_p95_processing_ms ?? null]
  const videoVals = [_round(stats?.video_avg_processing_ms), stats?.video_p50_processing_ms ?? null, stats?.video_p95_processing_ms ?? null]
  const hasImage = imageVals.some((v) => Number.isFinite(v))
  const hasVideo = videoVals.some((v) => Number.isFinite(v))

  if (!hasImage && !hasVideo) {
    return <AngleEmptyState icon={<Gauge size={26} aria-hidden="true" />} message={copy.insights.latencyEmpty} />
  }

  const trace = (name, vals, color) => ({
    name,
    type: 'bar',
    orientation: 'h',
    y: labels,
    x: vals,
    marker: { color },
    text: vals.map((v) => (Number.isFinite(v) ? `${v.toLocaleString()} ms` : '')),
    textposition: 'outside',
    textfont: { color: plotTheme.muted, size: 11 },
    cliponaxis: false,
    hovertemplate: `${name} · %{y}<br>%{x:,} ms<extra></extra>`,
  })
  const data = []
  if (hasImage) data.push(trace(copy.insights.latencyImages, imageVals, LATENCY_COLORS.image))
  if (hasVideo) data.push(trace(copy.insights.latencyVideos, videoVals, LATENCY_COLORS.video))

  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      copy={copy}
      ariaLabel={copy.insights.latencyTitle}
      data={data}
      layout={basePlotLayout(plotTheme, {
        height: 260,
        margin: { l: 96, r: 48, t: 10, b: 40 },
        barmode: 'group',
        showlegend: data.length > 1,
        legend: { orientation: 'h', y: 1.12, x: 0, font: { color: plotTheme.muted, size: 11 } },
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.latencyAxis, plotTheme),
          gridcolor: plotTheme.grid,
          rangemode: 'tozero',
          tickformat: ',d',
        }),
        yaxis: baseAxisStyle(plotTheme, { automargin: true }),
      })}
      useResizeHandler
    />
  )
}

export function InferencePerformance({ plotTheme, copy }) {
  const [filters, setFilters] = useState({})
  const models = useFetch(fetchModels, [])
  // keepPreviousData so the charts don't blink to empty between filter changes.
  const stats = useFetch(() => fetchStats(filters), [filters], { keepPreviousData: true })

  return (
    <>
      <StatsFilterBar
        value={filters}
        onChange={setFilters}
        models={models.data}
        count={stats.data?.total_analyses}
        copy={copy}
      />

      <article className="viz-card span-all">
        <div className="viz-heading">
          <Target size={18} />
          <div>
            <h3>{copy.insights.statsTitle}</h3>
            <p>{copy.insights.statsText}</p>
          </div>
        </div>
        {stats.loading && !stats.data ? (
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

      <article className="viz-card span-all">
        <div className="viz-heading">
          <Activity size={18} />
          <div>
            <h3>{copy.insights.latencyTitle}</h3>
            <p>{copy.insights.latencyText}</p>
          </div>
        </div>
        {stats.loading && !stats.data ? (
          <ChartSkeleton copy={copy} />
        ) : stats.error ? (
          <AngleEmptyState icon={<Gauge size={26} aria-hidden="true" />} message={copy.insights.loadError} />
        ) : (
          <LatencyChart stats={stats.data} plotTheme={plotTheme} copy={copy} />
        )}
      </article>
    </>
  )
}
