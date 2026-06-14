import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Star, Trash2, Upload, BarChart3, EyeOff, Eye } from 'lucide-react'
import { useModelManagement } from '../hooks/useModelManagement'
import { useDatasets } from '../hooks/useDatasets'
import { useJobs } from '../hooks/useJobs'
import { Modal } from '../components/lifecycle/Modal'
import { JobMonitor } from '../components/lifecycle/JobMonitor'
import { PapiGlyph } from '../components/PapiGlyph'

function metricValue(value) {
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

// One registry entry as a tactile card: provenance badges, headline metrics, and
// the lifecycle actions (promote / enable-disable / delete / evaluate / compare).
function ModelCard({ model, copy, busy, onPromote, onToggleDisabled, onDelete, onEvaluate, selected, onToggleCompare }) {
  const vm = model.val_metrics || {}
  const verdict = model.available ? 'go' : 'stop'
  return (
    <article className={`model-card${model.is_default ? ' model-card--default' : ''}`}>
      <header className="model-card__head">
        <PapiGlyph size="history" verdict={verdict} />
        <div className="model-card__titles">
          <h3 className="model-card__label">{model.model_label || model.model_id}</h3>
          <p className="model-card__meta mono">
            {copy.models.roles[model.model_role] ?? model.model_role} · {copy.models.sources[model.source] ?? model.source}
          </p>
        </div>
      </header>

      <div className="model-card__badges">
        {model.is_default && <span className="lc-badge lc-badge--default">{copy.models.badge.default}</span>}
        {model.protected && <span className="lc-badge">{copy.models.badge.protected}</span>}
        {model.disabled && <span className="lc-badge lc-badge--warn">{copy.models.badge.disabled}</span>}
        {!model.available && !model.disabled && (
          <span className="lc-badge lc-badge--warn">{copy.models.badge.unavailable}</span>
        )}
      </div>

      <dl className="model-card__metrics">
        <div><dt className="mono">mAP@50</dt><dd className="mono tnum">{metricValue(vm.map50)}</dd></div>
        <div><dt className="mono">mAP@50-95</dt><dd className="mono tnum">{metricValue(vm.map50_95)}</dd></div>
        <div><dt className="mono">P</dt><dd className="mono tnum">{metricValue(vm.precision)}</dd></div>
        <div><dt className="mono">R</dt><dd className="mono tnum">{metricValue(vm.recall)}</dd></div>
      </dl>
      <p className="model-card__sub mono">
        {copy.models.classesLabel}: {model.classes ? Object.keys(model.classes).length : model.class_count ?? '—'}
        {model.file_size_mb != null ? ` · ${model.file_size_mb} MB` : ''}
      </p>

      <div className="model-card__actions">
        {!model.is_default && model.available && (
          <button className="secondary-button" type="button" disabled={busy} onClick={() => onPromote(model)}>
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
        <label className="model-card__compare">
          <input type="checkbox" checked={selected} onChange={() => onToggleCompare(model.model_id)} />
          {copy.models.actions.compare}
        </label>
      </div>
    </article>
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

function EvaluateModal({ open, onClose, copy, model, datasets, onSubmit }) {
  const ready = datasets.filter((d) => d.status === 'ready')
  const [datasetId, setDatasetId] = useState('')
  const [split, setSplit] = useState('test')
  const [submitting, setSubmitting] = useState(false)

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
        <p className="lc-empty">{copy.models.evaluate.noDatasets}</p>
      ) : (
        <form className="lc-form" onSubmit={submit}>
          <p className="model-card__meta mono">{model?.model_label}</p>
          <label className="lc-field">
            <span>{copy.models.evaluate.dataset}</span>
            <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
              <option value="">—</option>
              {ready.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
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

function ComparePanel({ models, ids, copy }) {
  const chosen = models.filter((m) => ids.has(m.model_id))
  if (chosen.length < 2) {
    return null
  }
  const rows = [
    ['mAP@50', 'map50'],
    ['mAP@50-95', 'map50_95'],
    ['P', 'precision'],
    ['R', 'recall'],
  ]
  return (
    <section className="viz-card compare-panel" aria-label={copy.models.compare.title}>
      <h3 className="viz-heading">{copy.models.compare.title}</h3>
      <table className="compare-table">
        <thead>
          <tr>
            <th />
            {chosen.map((m) => (
              <th key={m.model_id} className="mono">{m.model_label || m.model_id}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, key]) => (
            <tr key={key}>
              <th scope="row" className="mono">{label}</th>
              {chosen.map((m) => (
                <td key={m.model_id} className="mono tnum">{metricValue(m.val_metrics?.[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export function ModelsPage({ copy, isAdmin }) {
  const { models, loading, error, upload, promote, setDisabled, remove, evaluate } = useModelManagement()
  const { datasets } = useDatasets()
  const { jobs, cancel } = useJobs()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [evalModel, setEvalModel] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [compareIds, setCompareIds] = useState(() => new Set())

  const evaluateJobs = useMemo(() => jobs.filter((job) => job.kind === 'evaluate'), [jobs])

  if (!isAdmin) {
    return (
      <section className="lc-page lc-gate">
        <PapiGlyph size="brand" />
        <h1>{copy.models.adminRequired}</h1>
        <p className="lc-empty">{copy.models.adminRequiredHint}</p>
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

      <JobMonitor jobs={evaluateJobs} onCancel={cancel} copy={copy} />

      {loading && <p className="lc-empty">{copy.models.loading}</p>}
      {error && <p className="lc-empty lc-empty--error">{copy.models.loadError}</p>}
      {!loading && models.length === 0 && <p className="lc-empty">{copy.models.empty}</p>}

      <div className="model-grid">
        {models.map((model) => (
          <ModelCard
            key={model.model_id}
            model={model}
            copy={copy}
            busy={busyId === model.model_id}
            selected={compareIds.has(model.model_id)}
            onToggleCompare={toggleCompare}
            onPromote={(m) =>
              withBusy(m.model_id, () => promote(m.model_id), copy.models.toast.promoted)
            }
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

      <ComparePanel models={models} ids={compareIds} copy={copy} />

      <UploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} copy={copy} onSubmit={handleUpload} />
      <EvaluateModal
        key={evalModel?.model_id || 'none'}
        open={Boolean(evalModel)}
        onClose={() => setEvalModel(null)}
        copy={copy}
        model={evalModel}
        datasets={datasets}
        onSubmit={handleEvaluate}
      />
    </section>
  )
}
