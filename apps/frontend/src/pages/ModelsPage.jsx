import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Star, Trash2, Upload, BarChart3, EyeOff, Eye, Info, X, Filter, Search, CloudSnow } from 'lucide-react'
import { useModelManagement } from '../hooks/useModelManagement'
import { useDatasets } from '../hooks/useDatasets'
import { useJobs } from '../hooks/useJobs'
import { fetchStats } from '../lib/api'
import { Modal } from '../components/lifecycle/Modal'
import { JobMonitor } from '../components/lifecycle/JobMonitor'
import { PapiGlyph } from '../components/PapiGlyph'
import { lampStateLabel } from '../lib/stateLabels'

// Number.isFinite (not typeof === 'number') so a stray NaN/Infinity renders the
// em-dash placeholder instead of the literal "NaN" — typeof NaN is 'number'.
function metricValue(value) {
  return Number.isFinite(value) ? value.toFixed(3) : '—'
}

function msValue(value) {
  return Number.isFinite(value) ? `${Math.round(value)} ms` : '—'
}

function intValue(value) {
  return Number.isFinite(value) ? value.toLocaleString() : '—'
}

function sizeValue(value) {
  return Number.isFinite(value) ? `${value} MB` : '—'
}

function textValue(value) {
  return value || '—'
}

function classCountOf(model) {
  // Null-safe: EvaluateModal computes a default dataset on every render, and `model`
  // is null while the dialog is closed — a bare model.classes there crashed the page.
  if (model?.classes) return Object.keys(model.classes).length
  return typeof model?.class_count === 'number' ? model.class_count : null
}

// Fixed display order for the synthetic-weather robustness bars — clear first as the
// baseline, snow last as the decisive differentiator (only a weather-trained model holds it).
const WEATHER_CONDITIONS = ['clear', 'rain', 'fog', 'haze', 'snow']

// A 0–1 detection score as a labelled bar: the fill makes "0.99 vs 0.51" legible at a
// glance (a column of bare numbers does not). Non-finite → empty track + em-dash.
function ScoreBar({ label, value }) {
  const finite = Number.isFinite(value)
  const pct = finite ? Math.max(0, Math.min(1, value)) * 100 : 0
  return (
    <div className="score-bar">
      <span className="score-bar__label mono">{label}</span>
      <span className="score-bar__track" aria-hidden="true">
        <span className="score-bar__fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="score-bar__value mono tnum">{metricValue(value)}</span>
    </div>
  )
}

// One registry entry as a tactile card: provenance badges, headline metrics, and
// the lifecycle actions (promote / enable-disable / delete / evaluate / compare).
function ModelCard({ model, copy, busy, onPromote, onToggleDisabled, onDelete, onEvaluate, selected, onToggleCompare }) {
  const vm = model.val_metrics || {}
  const verdict = model.available ? 'go' : 'stop'
  const classCount = classCountOf(model)
  const perClass = vm.per_class ? Object.entries(vm.per_class) : []
  return (
    <article
      className={`model-card${model.is_default ? ' model-card--default' : ''}${
        !model.available ? ' model-card--muted' : ''
      }`}
    >
      <header className="model-card__head">
        <PapiGlyph size="history" verdict={verdict} />
        <div className="model-card__titles">
          <h3 className="model-card__label">{model.model_label || model.model_id}</h3>
          <p className="model-card__meta mono">
            {copy.models.roles[model.model_role] ?? model.model_role} ·{' '}
            {copy.models.sources[model.source] ?? model.source}
          </p>
        </div>
        <label className="model-card__compare" title={copy.models.actions.compare}>
          <input type="checkbox" checked={selected} onChange={() => onToggleCompare(model.model_id)} />
          <span>{copy.models.actions.compare}</span>
        </label>
      </header>

      <div className="model-card__badges">
        {model.is_default && <span className="lc-badge lc-badge--default">{copy.models.badge.default}</span>}
        {model.protected && <span className="lc-badge">{copy.models.badge.protected}</span>}
        {model.disabled && <span className="lc-badge lc-badge--warn">{copy.models.badge.disabled}</span>}
        {!model.available && !model.disabled && (
          <span className="lc-badge lc-badge--warn">{copy.models.badge.unavailable}</span>
        )}
      </div>

      <div className="model-card__scores">
        <ScoreBar label={copy.insights.metricMap50} value={vm.map50} />
        <ScoreBar label={copy.insights.metricMap5095} value={vm.map50_95} />
        <ScoreBar label={copy.insights.metricPrecision} value={vm.precision} />
        <ScoreBar label={copy.insights.metricRecall} value={vm.recall} />
      </div>

      {/* Per-condition synthetic-weather robustness (mAP@0.5). Only the handful of models
          with a weather eval carry this; the snow bar is the headline. */}
      {model.weather_metrics && (
        <div className="model-card__weather">
          <h4 className="model-card__weather-title">
            <CloudSnow size={13} aria-hidden="true" />
            {copy.models.weather.title}
          </h4>
          <div className="model-card__scores">
            {WEATHER_CONDITIONS.map((cond) => (
              <ScoreBar key={cond} label={copy.models.weather[cond]} value={model.weather_metrics[cond]} />
            ))}
          </div>
          <p className="model-card__weather-note mono">{copy.models.weather.note}</p>
        </div>
      )}

      <div className="model-card__cred mono">
        <span><i>{copy.models.compare.split}</i>{textValue(model.dataset_split_evaluated)}</span>
        <span>
          <i>{copy.models.confLabel}</i>
          {Number.isFinite(model.confidence_threshold) ? `${Math.round(model.confidence_threshold * 100)}%` : '—'}
        </span>
        <span><i>{copy.models.compare.classes}</i>{classCount ?? '—'}</span>
        {model.file_size_mb != null && <span><i>{copy.models.compare.size}</i>{model.file_size_mb} MB</span>}
      </div>

      {/* Per-class precision/recall/F1 — the detail view that used to live on the
          Insights page; it belongs with the model now. Collapsed by default. */}
      {perClass.length > 0 && (
        <details className="model-card__perclass">
          <summary>{copy.insights.perClassChartTitle}</summary>
          <table className="model-per-class">
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col">{copy.insights.metricPrecision}</th>
                <th scope="col">{copy.insights.metricRecall}</th>
                <th scope="col">{copy.insights.metricF1}</th>
              </tr>
            </thead>
            <tbody>
              {perClass.map(([cls, row]) => (
                <tr key={cls}>
                  <th scope="row">{lampStateLabel(cls, copy)}</th>
                  <td className="tnum">{metricValue(row?.precision)}</td>
                  <td className="tnum">{metricValue(row?.recall)}</td>
                  <td className="tnum">{metricValue(row?.f1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {model.disabled_reason && !model.available && (
        <p className="model-card__reason">{model.disabled_reason}</p>
      )}

      <div className="model-card__actions">
        {!model.is_default && !model.disabled && (
          <button
            className="secondary-button"
            type="button"
            disabled={busy}
            title={copy.models.promoteHint}
            onClick={() => onPromote(model)}
          >
            <Star size={14} aria-hidden="true" /> {copy.models.actions.promote}
          </button>
        )}
        <button className="ghost-button" type="button" disabled={busy} onClick={() => onEvaluate(model)}>
          <BarChart3 size={14} aria-hidden="true" /> {copy.models.actions.evaluate}
        </button>
        {!model.protected && (
          <button
            className="ghost-button"
            type="button"
            disabled={busy}
            onClick={() => onToggleDisabled(model)}
          >
            {model.disabled ? <Eye size={14} aria-hidden="true" /> : <EyeOff size={14} aria-hidden="true" />}
            {model.disabled ? copy.models.actions.enable : copy.models.actions.disable}
          </button>
        )}
        {!model.protected && (
          <button className="ghost-button ghost-button--danger" type="button" disabled={busy} onClick={() => onDelete(model)}>
            <Trash2 size={14} aria-hidden="true" /> {copy.models.actions.delete}
          </button>
        )}
      </div>
    </article>
  )
}

// Quick status strip: model count, how many can actually serve, and the current
// default (the model used when a request names none — see the defaultHint banner).
function OverviewStrip({ models, copy }) {
  const total = models.length
  const available = models.filter((m) => m.available).length
  const def = models.find((m) => m.is_default)
  return (
    <div className="lc-overview" role="group" aria-label={copy.models.title}>
      <div className="lc-overview__stat">
        <span className="lc-overview__num tnum">{total}</span>
        <span className="lc-overview__label">{copy.models.overview.total}</span>
      </div>
      <div className="lc-overview__stat">
        <span className="lc-overview__num tnum">{available}</span>
        <span className="lc-overview__label">{copy.models.overview.available}</span>
      </div>
      <div className="lc-overview__stat lc-overview__stat--wide">
        <span className="lc-overview__num lc-overview__num--text">
          {def ? def.model_label || def.model_id : copy.models.overview.none}
        </span>
        <span className="lc-overview__label">{copy.models.overview.defaultModel}</span>
      </div>
    </div>
  )
}

// Plain-language guide to the evaluation metrics on the cards + compare table.
// A collapsed disclosure so it informs on demand without crowding the grid; the
// metric names reuse the same copy keys as the score bars so they read identically.
function MetricsGuide({ copy }) {
  const guide = copy.models.metricsGuide
  const rows = [
    { term: copy.insights.metricMap50, desc: guide.map50 },
    { term: copy.insights.metricMap5095, desc: guide.map5095 },
    { term: copy.insights.metricPrecision, desc: guide.precision },
    { term: copy.insights.metricRecall, desc: guide.recall },
    { term: copy.insights.metricF1, desc: guide.f1 },
  ]
  return (
    <details className="metric-guide">
      <summary className="metric-guide__summary">
        <Info size={15} aria-hidden="true" />
        <span>{guide.title}</span>
      </summary>
      <dl className="metric-guide__list">
        {rows.map((row) => (
          <div className="metric-guide__item" key={row.term}>
            <dt className="mono">{row.term}</dt>
            <dd>{row.desc}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}

function UploadModal({ open, onClose, copy, onSubmit }) {
  const [file, setFile] = useState(null)
  const [label, setLabel] = useState('')
  const [role, setRole] = useState('detector')
  const [description, setDescription] = useState('')
  const [makeDefault, setMakeDefault] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (!file || !label.trim()) {
      toast.error(copy.models.upload.missingFields)
      return
    }
    setSubmitting(true)
    try {
      await onSubmit({ file, label: label.trim(), role, description, makeDefault })
      onClose()
      setFile(null)
      setLabel('')
      setDescription('')
      setMakeDefault(false)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={copy.models.upload.title} closeLabel={copy.models.close}>
      <form className="lc-form" onSubmit={submit}>
        <p className="lc-warning">{copy.models.upload.pickleWarning}</p>
        <label className="lc-field">
          <span>{copy.models.upload.file}</span>
          <input
            type="file"
            accept=".pt,.onnx"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <small>{copy.models.upload.fileHint}</small>
        </label>
        <label className="lc-field">
          <span>{copy.models.upload.label}</span>
          <input type="text" value={label} onChange={(event) => setLabel(event.target.value)} />
        </label>
        <label className="lc-field">
          <span>{copy.models.upload.role}</span>
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="detector">{copy.models.upload.roleDetector}</option>
            <option value="transition">{copy.models.upload.roleTransition}</option>
          </select>
        </label>
        <label className="lc-field">
          <span>{copy.models.upload.description}</span>
          <input type="text" value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <label className="lc-check">
          <input type="checkbox" checked={makeDefault} onChange={(event) => setMakeDefault(event.target.checked)} />
          {copy.models.upload.makeDefault}
        </label>
        <button className="cta-button" type="submit" disabled={submitting}>
          {submitting ? copy.models.upload.submitting : copy.models.upload.submit}
        </button>
      </form>
    </Modal>
  )
}

// Default the Evaluate dialog to the built-in eval set that matches the model's
// class count (2-class detector -> red/white set; 3-class -> transition set), so
// a model can be scored out of the box on classes it actually predicts.
function pickDefaultDataset(ready, model) {
  if (!ready.length) return ''
  const cc = classCountOf(model)
  const builtins = ready.filter((d) => d.source === 'builtin')
  const byClass = builtins.find((d) => d.class_names && Object.keys(d.class_names).length === cc)
  return (byClass || builtins[0] || ready[0]).id
}

function EvaluateModal({ open, onClose, copy, model, datasets, datasetsLoading, onSubmit }) {
  const ready = datasets.filter((d) => d.status === 'ready')
  // Derive the selection instead of storing it: `picked` stays null until the user
  // explicitly chooses, so the role-matched default is recomputed each render and is
  // adopted automatically once /api/datasets resolves (the modal is often opened
  // before the list loads). This avoids a setState-in-effect render cascade while
  // still letting the user override — selecting the '—' option sets picked to '',
  // which disables submit as before.
  const [picked, setPicked] = useState(null)
  // Only resolve a default when there's a model (the dialog is open) — pickDefaultDataset
  // reads the model's class count, and `model` is null while the dialog is closed.
  const datasetId = picked ?? (model ? pickDefaultDataset(ready, model) : '')
  const [split, setSplit] = useState('test')
  const [submitting, setSubmitting] = useState(false)
  const selectedIsBuiltin = ready.some((d) => d.id === datasetId && d.source === 'builtin')

  const submit = async (event) => {
    event.preventDefault()
    if (!datasetId) return
    setSubmitting(true)
    try {
      await onSubmit(model, { datasetId, split })
      onClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={copy.models.evaluate.title} closeLabel={copy.models.close}>
      {ready.length === 0 ? (
        // Distinguish "still loading" from "genuinely none" — otherwise opening
        // Evaluate before the dataset list resolves shows a dead-end "upload one
        // first" even though the built-in eval sets are about to appear.
        <p className="lc-empty">{datasetsLoading ? copy.models.loading : copy.models.evaluate.noDatasets}</p>
      ) : (
        <form className="lc-form" onSubmit={submit}>
          <p className="model-card__meta mono">{model?.model_label}</p>
          <label className="lc-field">
            <span>{copy.models.evaluate.dataset}</span>
            <select value={datasetId} onChange={(event) => setPicked(event.target.value)}>
              <option value="">—</option>
              {ready.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            {selectedIsBuiltin && <small>{copy.models.evaluate.defaultHint}</small>}
          </label>
          <label className="lc-field">
            <span>{copy.models.evaluate.split}</span>
            <select value={split} onChange={(event) => setSplit(event.target.value)}>
              <option value="test">test</option>
              <option value="val">val</option>
            </select>
          </label>
          <button className="cta-button" type="submit" disabled={submitting || !datasetId}>
            {copy.models.evaluate.submit}
          </button>
        </form>
      )}
    </Modal>
  )
}

// Highlight the winning cell(s) per row: the highest value for accuracy rows, the
// lowest for latency. Returns the empty set when it would be meaningless (a single
// number, all-equal, or a non-ranked row) so nothing is misleadingly flagged.
function bestValueSet(values, better) {
  if (!better) return new Set()
  // Number.isFinite excludes NaN/Infinity, so Math.max/min can't return NaN.
  const nums = values.filter((v) => Number.isFinite(v))
  if (nums.length < 2 || nums.every((v) => v === nums[0])) return new Set()
  const target = better === 'high' ? Math.max(...nums) : Math.min(...nums)
  return new Set(nums.filter((v) => v === target))
}

function ComparePanel({ models, ids, copy, onClear }) {
  const chosen = models.filter((m) => ids.has(m.model_id))
  // Sorted, stable key so the per-model stats effect only refires when the SET of
  // compared models changes (not on every parent render).
  const idKey = chosen
    .map((m) => m.model_id)
    .sort()
    .join(',')
  const [stats, setStats] = useState({})
  const fetchedRef = useRef(new Set())

  useEffect(() => {
    let active = true
    const idsArr = idKey ? idKey.split(',') : []
    // Per-model inference latency comes from the logged-analyses aggregate
    // (/api/stats?model_id=…). Fetch once per id, only when a comparison is shown.
    if (idsArr.length < 2) return undefined
    idsArr.forEach((id) => {
      if (fetchedRef.current.has(id)) return
      fetchedRef.current.add(id)
      setStats((cur) => ({ ...cur, [id]: { state: 'loading' } }))
      fetchStats({ modelId: id })
        .then((data) => {
          if (active) setStats((cur) => ({ ...cur, [id]: { state: 'ok', data } }))
        })
        .catch(() => {
          if (active) setStats((cur) => ({ ...cur, [id]: { state: 'error' } }))
        })
    })
    return () => {
      active = false
    }
  }, [idKey])

  if (chosen.length < 2) {
    return null
  }

  const statOf = (id) => (stats[id]?.state === 'ok' ? stats[id].data : null)

  const classNames = Array.from(
    new Set(chosen.flatMap((m) => Object.keys(m.val_metrics?.per_class || {}))),
  ).sort()
  const hasWeather = chosen.some((m) => m.weather_metrics)

  const groups = [
    {
      title: copy.models.compare.groupAccuracy,
      rows: [
        { label: copy.insights.metricMap50, get: (m) => m.val_metrics?.map50, better: 'high', fmt: metricValue, bar: true },
        { label: copy.insights.metricMap5095, get: (m) => m.val_metrics?.map50_95, better: 'high', fmt: metricValue, bar: true },
        { label: copy.insights.metricPrecision, get: (m) => m.val_metrics?.precision, better: 'high', fmt: metricValue, bar: true },
        { label: copy.insights.metricRecall, get: (m) => m.val_metrics?.recall, better: 'high', fmt: metricValue, bar: true },
      ],
    },
    ...(classNames.length
      ? [
          {
            title: copy.models.compare.groupPerClass,
            rows: classNames.map((cls) => ({
              label: `F1 · ${lampStateLabel(cls, copy)}`,
              get: (m) => m.val_metrics?.per_class?.[cls]?.f1,
              better: 'high',
              fmt: metricValue,
              bar: true,
            })),
          },
        ]
      : []),
    ...(hasWeather
      ? [
          {
            title: copy.models.compare.groupWeather,
            rows: WEATHER_CONDITIONS.map((cond) => ({
              label: copy.models.weather[cond],
              get: (m) => m.weather_metrics?.[cond],
              better: 'high',
              fmt: metricValue,
              bar: true,
            })),
          },
        ]
      : []),
    {
      title: copy.models.compare.groupInference,
      // Latency is split by media type: a whole-video analysis spans many frames,
      // so its processing time is not comparable to a single image's.
      rows: [
        { label: `${copy.models.compare.median} · ${copy.models.compare.mediaImage}`, get: (m) => statOf(m.model_id)?.image_p50_processing_ms, better: 'low', fmt: msValue },
        { label: `${copy.models.compare.median} · ${copy.models.compare.mediaVideo}`, get: (m) => statOf(m.model_id)?.video_p50_processing_ms, better: 'low', fmt: msValue },
        { label: `${copy.models.compare.p95} · ${copy.models.compare.mediaImage}`, get: (m) => statOf(m.model_id)?.image_p95_processing_ms, better: 'low', fmt: msValue },
        { label: `${copy.models.compare.p95} · ${copy.models.compare.mediaVideo}`, get: (m) => statOf(m.model_id)?.video_p95_processing_ms, better: 'low', fmt: msValue },
        { label: copy.models.compare.samples, get: (m) => statOf(m.model_id)?.total_analyses, better: null, fmt: intValue },
      ],
    },
    {
      title: copy.models.compare.groupModel,
      rows: [
        { label: copy.models.compare.size, get: (m) => m.file_size_mb, better: null, fmt: sizeValue },
        { label: copy.models.compare.classes, get: (m) => classCountOf(m), better: null, fmt: intValue },
        { label: copy.models.compare.source, get: (m) => copy.models.sources[m.source] ?? m.source, better: null, fmt: textValue },
        { label: copy.models.compare.split, get: (m) => m.dataset_split_evaluated, better: null, fmt: textValue },
      ],
    },
  ]

  return (
    <section className="viz-card compare-panel" aria-label={copy.models.compare.title}>
      <div className="compare-panel__head">
        <h3 className="viz-heading">{copy.models.compare.title}</h3>
        <button className="ghost-button" type="button" onClick={onClear}>
          <X size={14} aria-hidden="true" /> {copy.models.compare.clear}
        </button>
      </div>
      <div className="compare-scroll">
        <table className="compare-table">
          <thead>
            <tr>
              <th scope="col" />
              {chosen.map((m) => (
                <th key={m.model_id} className="mono" scope="col">
                  {m.model_label || m.model_id}
                  {m.is_default && <span className="compare-th__tag">{copy.models.badge.default}</span>}
                </th>
              ))}
            </tr>
          </thead>
          {/* One <tbody> per metric group so assistive tech announces them as
              distinct row groups; the section title is a full-width header row. */}
          {groups.map((group) => (
            <tbody key={group.title}>
              <tr className="compare-group">
                <th colSpan={chosen.length + 1}>{group.title}</th>
              </tr>
              {group.rows.map((row) => {
                const values = chosen.map((m) => row.get(m))
                const best = bestValueSet(values, row.better)
                return (
                  <tr key={`${group.title}:${row.label}`}>
                    <th scope="row" className="mono">
                      {row.label}
                    </th>
                    {chosen.map((m, i) => {
                      const value = values[i]
                      const isBest = Number.isFinite(value) && best.has(value)
                      // 0–1 score rows get an inline bar so a column scan reads the
                      // relative gap, not just the digits; other rows stay plain.
                      const showBar = row.bar && Number.isFinite(value)
                      return (
                        <td key={m.model_id} className={`mono tnum${isBest ? ' compare-best' : ''}`}>
                          {showBar ? (
                            <span className="compare-cell">
                              <span className="compare-cell__track" aria-hidden="true">
                                <span
                                  className="compare-cell__fill"
                                  style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
                                />
                              </span>
                              <span className="compare-cell__num">{row.fmt(value)}</span>
                            </span>
                          ) : (
                            row.fmt(value)
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          ))}
        </table>
      </div>
      <p className="compare-note">{copy.models.compare.inferenceNote}</p>
    </section>
  )
}

const DEFAULT_FILTERS = { query: '', role: 'all', status: 'all', sort: 'default' }

// Pure filter+sort over the registry. Search matches label OR id; role/status narrow
// the set; sort reorders (registry order is the default and preserves the backend's
// served-first ordering). Kept out of the component so it is trivially testable and
// memoisable.
function filterAndSortModels(models, filters) {
  const q = filters.query.trim().toLowerCase()
  const list = models.filter((m) => {
    if (q && !`${m.model_label || ''} ${m.model_id || ''}`.toLowerCase().includes(q)) return false
    if (filters.role !== 'all' && (m.model_role || 'detector') !== filters.role) return false
    if (filters.status === 'available' && !m.available) return false
    if (filters.status === 'unavailable' && m.available) return false
    return true
  })
  const sorted = [...list]
  if (filters.sort === 'name') {
    sorted.sort((a, b) => (a.model_label || a.model_id || '').localeCompare(b.model_label || b.model_id || ''))
  } else if (filters.sort === 'accuracy') {
    const acc = (m) => (Number.isFinite(m.val_metrics?.map50) ? m.val_metrics.map50 : -1)
    sorted.sort((a, b) => acc(b) - acc(a))
  } else if (filters.sort === 'classes') {
    sorted.sort((a, b) => (classCountOf(b) ?? 0) - (classCountOf(a) ?? 0))
  }
  return sorted
}

// Search + role/status filters + sort for the registry grid. Presentational and
// controlled: the parent owns `filters` and recomputes the visible set.
function ModelsToolbar({ filters, onChange, count, total, copy }) {
  const t = copy.models.toolbar
  const active =
    filters.query !== '' || filters.role !== 'all' || filters.status !== 'all' || filters.sort !== 'default'
  return (
    <div className="models-toolbar" role="group" aria-label={t.title}>
      <span className="models-toolbar__title">
        <Filter size={15} aria-hidden="true" />
        {t.title}
      </span>

      <label className="stats-filter models-toolbar__search">
        <span>{t.search}</span>
        <span className="models-toolbar__search-field">
          <Search size={14} aria-hidden="true" />
          <input
            type="search"
            value={filters.query}
            placeholder={t.searchPlaceholder}
            onChange={(event) => onChange({ query: event.target.value })}
            aria-label={t.search}
          />
        </span>
      </label>

      <label className="stats-filter">
        <span>{t.role}</span>
        <select value={filters.role} onChange={(event) => onChange({ role: event.target.value })} aria-label={t.role}>
          <option value="all">{t.roleAll}</option>
          <option value="detector">{copy.models.roles.detector}</option>
          <option value="transition">{copy.models.roles.transition}</option>
        </select>
      </label>

      <label className="stats-filter">
        <span>{t.status}</span>
        <select
          value={filters.status}
          onChange={(event) => onChange({ status: event.target.value })}
          aria-label={t.status}
        >
          <option value="all">{t.statusAll}</option>
          <option value="available">{t.statusAvailable}</option>
          <option value="unavailable">{t.statusUnavailable}</option>
        </select>
      </label>

      <label className="stats-filter">
        <span>{t.sort}</span>
        <select value={filters.sort} onChange={(event) => onChange({ sort: event.target.value })} aria-label={t.sort}>
          <option value="default">{t.sortDefault}</option>
          <option value="name">{t.sortName}</option>
          <option value="accuracy">{t.sortAccuracy}</option>
          <option value="classes">{t.sortClasses}</option>
        </select>
      </label>

      {active && (
        <button type="button" className="ghost-button models-toolbar__reset" onClick={() => onChange({ reset: true })}>
          <X size={15} aria-hidden="true" /> {t.reset}
        </button>
      )}

      <span className="models-toolbar__count mono" aria-live="polite">
        {t.results.replace('{count}', count).replace('{total}', total)}
      </span>
    </div>
  )
}

export function ModelsPage({ copy, isAdmin }) {
  const { models, loading, error, upload, promote, setDisabled, remove, evaluate } = useModelManagement()
  const { datasets, loading: datasetsLoading } = useDatasets()
  const { jobs, cancel, dismiss, clearFinished } = useJobs()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [evalModel, setEvalModel] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [compareIds, setCompareIds] = useState(() => new Set())
  const [filters, setFilters] = useState(DEFAULT_FILTERS)

  const evaluateJobs = useMemo(() => jobs.filter((job) => job.kind === 'evaluate'), [jobs])
  const visibleModels = useMemo(() => filterAndSortModels(models, filters), [models, filters])
  const onFilterChange = (patch) =>
    setFilters((prev) => (patch.reset ? DEFAULT_FILTERS : { ...prev, ...patch }))

  if (!isAdmin) {
    return (
      <section className="lc-page lc-gate">
        <PapiGlyph size="brand" />
        <h1>{copy.models.adminRequired}</h1>
        <p className="lc-empty">{copy.models.adminRequiredHint}</p>
        <Link className="cta-button" to="/login" state={{ from: { pathname: '/models' } }}>
          {copy.admin.signIn}
        </Link>
      </section>
    )
  }

  const withBusy = async (id, fn, successMsg) => {
    setBusyId(id)
    try {
      await fn()
      if (successMsg) toast.success(successMsg)
    } catch (err) {
      toast.error(err?.message || copy.models.toast.error)
    } finally {
      setBusyId(null)
    }
  }

  const handleUpload = async (payload) => {
    try {
      const created = await upload(payload)
      toast.success(copy.models.toast.uploaded.replace('{label}', created.model_label || ''))
    } catch (err) {
      toast.error(err?.message || copy.models.toast.error)
      throw err
    }
  }

  const handleEvaluate = async (model, body) => {
    try {
      await evaluate(model.model_id, body)
      toast.success(copy.models.toast.evalStarted)
    } catch (err) {
      toast.error(err?.message || copy.models.toast.error)
      throw err
    }
  }

  const handlePromote = (model) => {
    // The backend allows promoting any non-disabled model, including one whose
    // weights are not present in THIS deployment (so the operator can always
    // restore the canonical serving model as default). Warn first so an
    // unservable default is never set by accident.
    if (!model.available && !window.confirm(copy.models.promoteUnavailableConfirm)) {
      return
    }
    withBusy(model.model_id, () => promote(model.model_id), copy.models.toast.promoted)
  }

  const toggleCompare = (id) =>
    setCompareIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <section className="lc-page">
      <header className="lc-page__head">
        <div>
          <h1 className="lc-page__title">{copy.models.title}</h1>
          <p className="lc-page__subtitle">{copy.models.subtitle}</p>
        </div>
        <button className="cta-button" type="button" onClick={() => setUploadOpen(true)}>
          <Upload size={16} aria-hidden="true" /> {copy.models.uploadCta}
        </button>
      </header>

      <p className="lc-hint">
        <Info size={15} aria-hidden="true" />
        <span>{copy.models.defaultHint}</span>
      </p>

      <JobMonitor
        jobs={evaluateJobs}
        onCancel={cancel}
        onDismiss={dismiss}
        onClearFinished={() => clearFinished('evaluate')}
        copy={copy}
      />

      {loading && <p className="lc-empty">{copy.models.loading}</p>}
      {error && <p className="lc-empty lc-empty--error">{copy.models.loadError}</p>}
      {!loading && models.length === 0 && <p className="lc-empty">{copy.models.empty}</p>}

      {models.length > 0 && <OverviewStrip models={models} copy={copy} />}

      {models.length > 0 && <MetricsGuide copy={copy} />}

      {models.length > 0 && (
        <ModelsToolbar
          filters={filters}
          onChange={onFilterChange}
          count={visibleModels.length}
          total={models.length}
          copy={copy}
        />
      )}

      <div className="model-grid">
        {visibleModels.map((model) => (
          <ModelCard
            key={model.model_id}
            model={model}
            copy={copy}
            busy={busyId === model.model_id}
            selected={compareIds.has(model.model_id)}
            onToggleCompare={toggleCompare}
            onPromote={handlePromote}
            onToggleDisabled={(m) =>
              withBusy(
                m.model_id,
                () => setDisabled(m.model_id, !m.disabled),
                m.disabled ? copy.models.toast.enabled : copy.models.toast.disabled,
              )
            }
            onDelete={(m) => {
              if (window.confirm(copy.models.confirmDelete.replace('{label}', m.model_label || m.model_id))) {
                withBusy(m.model_id, () => remove(m.model_id), copy.models.toast.deleted)
              }
            }}
            onEvaluate={(m) => setEvalModel(m)}
          />
        ))}
      </div>

      {models.length > 0 && visibleModels.length === 0 && (
        <p className="lc-empty">{copy.models.toolbar.noMatch}</p>
      )}

      <ComparePanel models={models} ids={compareIds} copy={copy} onClear={() => setCompareIds(new Set())} />

      {/* key tied to open state so the form remounts fresh each time — otherwise
          typed-but-not-submitted fields linger and reappear on the next open. */}
      <UploadModal
        key={uploadOpen ? 'upload-open' : 'upload-closed'}
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        copy={copy}
        onSubmit={handleUpload}
      />
      <EvaluateModal
        key={evalModel?.model_id || 'none'}
        open={Boolean(evalModel)}
        onClose={() => setEvalModel(null)}
        copy={copy}
        model={evalModel}
        datasets={datasets}
        datasetsLoading={datasetsLoading}
        onSubmit={handleEvaluate}
      />
    </section>
  )
}
