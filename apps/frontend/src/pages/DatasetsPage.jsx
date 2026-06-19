import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Upload, Wand2, Trash2, GraduationCap, ClipboardCheck } from 'lucide-react'
import { useDatasets } from '../hooks/useDatasets'
import { useModelManagement } from '../hooks/useModelManagement'
import { useJobs } from '../hooks/useJobs'
import { Modal } from '../components/lifecycle/Modal'
import { JobMonitor } from '../components/lifecycle/JobMonitor'
import { LabelReview } from '../components/lifecycle/LabelReview'
import { PapiGlyph } from '../components/PapiGlyph'
import { downloadTrainingBundle, prepareTraining } from '../lib/api'

function DatasetCard({ dataset, copy, busy, onReview, onTrain, onDelete }) {
  return (
    <article className="dataset-card">
      <header className="dataset-card__head">
        <h3 className="dataset-card__name">{dataset.name}</h3>
        <div className="model-card__badges">
          {dataset.source === 'builtin' && <span className="lc-badge">{copy.datasets.sources.builtin}</span>}
          {dataset.source === 'project' && <span className="lc-badge">{copy.datasets.sources.project}</span>}
          <span className={`lc-badge lc-badge--${dataset.status === 'ready' ? 'default' : 'warn'}`}>
            {copy.datasets.statuses[dataset.status] ?? dataset.status}
          </span>
        </div>
      </header>
      <p className="dataset-card__meta mono">
        {copy.datasets.sources[dataset.source] ?? dataset.source} ·{' '}
        {copy.datasets.card.classesLabel}: {dataset.class_names ? Object.keys(dataset.class_names).length : '—'}
      </p>
      <dl className="dataset-card__counts">
        <div><dt className="mono">train</dt><dd className="mono tnum">{dataset.n_train}</dd></div>
        <div><dt className="mono">val</dt><dd className="mono tnum">{dataset.n_val}</dd></div>
        <div><dt className="mono">test</dt><dd className="mono tnum">{dataset.n_test}</dd></div>
      </dl>
      <div className="dataset-card__actions">
        {dataset.source === 'assisted' && dataset.status === 'labeling' && (
          <button className="secondary-button" type="button" onClick={() => onReview(dataset)}>
            <ClipboardCheck size={14} aria-hidden="true" /> {copy.datasets.card.review}
          </button>
        )}
        {dataset.status === 'ready' && dataset.source !== 'builtin' && (
          <button className="secondary-button" type="button" onClick={() => onTrain(dataset)}>
            <GraduationCap size={14} aria-hidden="true" /> {copy.datasets.card.train}
          </button>
        )}
        {dataset.source !== 'builtin' && dataset.source !== 'project' && (
          <button
            className="ghost-button ghost-button--danger"
            type="button"
            disabled={busy}
            onClick={() => onDelete(dataset)}
          >
            <Trash2 size={14} aria-hidden="true" /> {copy.datasets.card.delete}
          </button>
        )}
      </div>
    </article>
  )
}

function BundleUploadModal({ open, onClose, copy, onSubmit }) {
  const [file, setFile] = useState(null)
  const [name, setName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submit = async (event) => {
    event.preventDefault()
    if (!file || !name.trim()) return
    setSubmitting(true)
    try {
      await onSubmit({ file, name: name.trim() })
      onClose()
      setFile(null)
      setName('')
    } finally {
      setSubmitting(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={copy.datasets.upload.title} closeLabel={copy.models.close}>
      <form className="lc-form" onSubmit={submit}>
        <label className="lc-field">
          <span>{copy.datasets.upload.file}</span>
          <input type="file" accept=".zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <small>{copy.datasets.upload.fileHint}</small>
        </label>
        <label className="lc-field">
          <span>{copy.datasets.upload.name}</span>
          <input type="text" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <button className="cta-button" type="submit" disabled={submitting}>
          {submitting ? copy.datasets.upload.submitting : copy.datasets.upload.submit}
        </button>
      </form>
    </Modal>
  )
}

function AssistedModal({ open, onClose, copy, models, modelsLoading, onSubmit }) {
  const usable = models.filter((m) => m.available)
  const [files, setFiles] = useState([])
  const [name, setName] = useState('')
  const [modelId, setModelId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submit = async (event) => {
    event.preventDefault()
    if (!files.length || !name.trim() || !modelId) return
    setSubmitting(true)
    try {
      await onSubmit({ files, name: name.trim(), modelId })
      onClose()
      setFiles([])
      setName('')
    } finally {
      setSubmitting(false)
    }
  }
  return (
    <Modal open={open} onClose={onClose} title={copy.datasets.assisted.title} closeLabel={copy.models.close}>
      {usable.length === 0 ? (
        // Don't show the dead-end "no models" message while the registry is still
        // loading — that reads as a hard failure when models are about to arrive.
        <p className="lc-empty">{modelsLoading ? copy.datasets.loading : copy.datasets.assisted.noModels}</p>
      ) : (
        <form className="lc-form" onSubmit={submit}>
          <label className="lc-field">
            <span>{copy.datasets.assisted.files}</span>
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            />
            <small>{copy.datasets.assisted.filesHint}</small>
          </label>
          <label className="lc-field">
            <span>{copy.datasets.assisted.name}</span>
            <input type="text" value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="lc-field">
            <span>{copy.datasets.assisted.model}</span>
            <select value={modelId} onChange={(event) => setModelId(event.target.value)}>
              <option value="">—</option>
              {usable.map((m) => (
                <option key={m.model_id} value={m.model_id}>{m.model_label || m.model_id}</option>
              ))}
            </select>
          </label>
          <button className="cta-button" type="submit" disabled={submitting || !modelId || !files.length}>
            {submitting ? copy.datasets.assisted.submitting : copy.datasets.assisted.submit}
          </button>
        </form>
      )}
    </Modal>
  )
}

function TrainModal({ open, onClose, copy, dataset, models, onPrepared }) {
  const [baseModelId, setBaseModelId] = useState('')
  const [hyper, setHyper] = useState({ epochs: 80, imgsz: 1280, batch: 4, oversample: 4 })
  const [command, setCommand] = useState(null)
  const [busy, setBusy] = useState(false)

  const setField = (key) => (event) => setHyper((h) => ({ ...h, [key]: Number(event.target.value) }))

  const runPrepare = async () => {
    setBusy(true)
    try {
      const result = await prepareTraining({ datasetId: dataset.id, baseModelId, hyperparams: hyper })
      setCommand(result.command)
      await downloadTrainingBundle(result.job_id, `papi-training-${dataset.name}.zip`)
      onPrepared?.()
    } catch (err) {
      toast.error(err?.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={copy.datasets.train.title} closeLabel={copy.models.close} wide>
      <div className="lc-form">
        <p className="model-card__meta mono">{dataset?.name}</p>
        <label className="lc-field">
          <span>{copy.datasets.train.base}</span>
          <select value={baseModelId} onChange={(event) => setBaseModelId(event.target.value)}>
            <option value="">{copy.datasets.train.baseDefault}</option>
            {models.filter((m) => m.available).map((m) => (
              <option key={m.model_id} value={m.model_id}>{m.model_label || m.model_id}</option>
            ))}
          </select>
        </label>
        <div className="hyper-grid">
          <label className="lc-field"><span>{copy.datasets.train.epochs}</span>
            <input type="number" min="1" value={hyper.epochs} onChange={setField('epochs')} /></label>
          <label className="lc-field"><span>{copy.datasets.train.imgsz}</span>
            <input type="number" min="320" step="32" value={hyper.imgsz} onChange={setField('imgsz')} /></label>
          <label className="lc-field"><span>{copy.datasets.train.batch}</span>
            <input type="number" min="1" value={hyper.batch} onChange={setField('batch')} /></label>
          <label className="lc-field"><span>{copy.datasets.train.oversample}</span>
            <input type="number" min="1" value={hyper.oversample} onChange={setField('oversample')} /></label>
        </div>

        <div className="train-options">
          <div className="train-option">
            <h4>{copy.datasets.train.prepare}</h4>
            <p className="lc-empty">{copy.datasets.train.prepareDesc}</p>
            <button className="cta-button" type="button" onClick={runPrepare} disabled={busy}>
              {copy.datasets.train.submitPrepare}
            </button>
          </div>
        </div>

        {command && (
          <div className="train-command">
            <p className="lc-page__subtitle">{copy.datasets.train.prepareReady}</p>
            <code className="mono">{command}</code>
          </div>
        )}
      </div>
    </Modal>
  )
}

export function DatasetsPage({ copy, isAdmin }) {
  const { datasets, loading, error, uploadBundle, startAssisted, remove } = useDatasets()
  const { models, loading: modelsLoading } = useModelManagement()
  const { jobs, cancel, dismiss, clearFinished, refetch: refetchJobs, actionError: jobsActionError } =
    useJobs()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [assistedOpen, setAssistedOpen] = useState(false)
  const [reviewDataset, setReviewDataset] = useState(null)
  const [trainDataset, setTrainDataset] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const trainingJobs = useMemo(
    () => jobs.filter((job) => ['label_assist', 'train_prepare'].includes(job.kind)),
    [jobs],
  )

  if (!isAdmin) {
    return (
      <section className="lc-page lc-gate">
        <PapiGlyph size="brand" />
        <h1>{copy.models.adminRequired}</h1>
        <p className="lc-empty">{copy.models.adminRequiredHint}</p>
        <Link className="cta-button" to="/login" state={{ from: { pathname: '/datasets' } }}>
          {copy.admin.signIn}
        </Link>
      </section>
    )
  }

  const handleUpload = async (payload) => {
    try {
      await uploadBundle(payload)
      toast.success(copy.datasets.toast.uploaded)
    } catch (err) {
      toast.error(err?.message || copy.datasets.toast.error)
      throw err
    }
  }
  const handleAssisted = async (payload) => {
    try {
      await startAssisted(payload)
      toast.success(copy.datasets.toast.assistedStarted)
    } catch (err) {
      toast.error(err?.message || copy.datasets.toast.error)
      throw err
    }
  }
  const handleDelete = async (dataset) => {
    if (!window.confirm(copy.datasets.card.confirmDelete.replace('{name}', dataset.name))) return
    setBusyId(dataset.id)
    try {
      await remove(dataset.id)
      toast.success(copy.datasets.toast.deleted)
    } catch (err) {
      toast.error(err?.message || copy.datasets.toast.error)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="lc-page">
      <header className="lc-page__head">
        <div>
          <h1 className="lc-page__title">{copy.datasets.title}</h1>
          <p className="lc-page__subtitle">{copy.datasets.subtitle}</p>
        </div>
        <div className="lc-page__head-actions">
          <button className="secondary-button" type="button" onClick={() => setAssistedOpen(true)}>
            <Wand2 size={16} aria-hidden="true" /> {copy.datasets.assistedCta}
          </button>
          <button className="cta-button" type="button" onClick={() => setUploadOpen(true)}>
            <Upload size={16} aria-hidden="true" /> {copy.datasets.uploadCta}
          </button>
        </div>
      </header>

      <JobMonitor
        jobs={trainingJobs}
        onCancel={cancel}
        onDismiss={dismiss}
        onClearFinished={() =>
          Promise.all([clearFinished('label_assist'), clearFinished('train_prepare')])
        }
        actionError={jobsActionError}
        copy={copy}
      />

      {loading && <p className="lc-empty">{copy.datasets.loading}</p>}
      {error && <p className="lc-empty lc-empty--error">{copy.datasets.loadError}</p>}
      {!loading && datasets.length === 0 && <p className="lc-empty">{copy.datasets.empty}</p>}

      <div className="dataset-grid">
        {datasets.map((dataset) => (
          <DatasetCard
            key={dataset.id}
            dataset={dataset}
            copy={copy}
            busy={busyId === dataset.id}
            onReview={(d) => setReviewDataset(d)}
            onTrain={(d) => setTrainDataset(d)}
            onDelete={handleDelete}
          />
        ))}
      </div>

      {/* key tied to open state so each modal remounts fresh — otherwise typed
          fields linger and reappear when reopened after a cancel. */}
      <BundleUploadModal
        key={uploadOpen ? 'bundle-open' : 'bundle-closed'}
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        copy={copy}
        onSubmit={handleUpload}
      />
      <AssistedModal
        key={assistedOpen ? 'assisted-open' : 'assisted-closed'}
        open={assistedOpen}
        onClose={() => setAssistedOpen(false)}
        copy={copy}
        models={models}
        modelsLoading={modelsLoading}
        onSubmit={handleAssisted}
      />
      <Modal
        open={Boolean(reviewDataset)}
        onClose={() => setReviewDataset(null)}
        title={copy.datasets.review.title}
        closeLabel={copy.models.close}
        wide
      >
        {reviewDataset && (
          <LabelReview
            datasetId={reviewDataset.id}
            classNames={reviewDataset.class_names}
            copy={copy}
            onCommitted={() => {
              setReviewDataset(null)
            }}
          />
        )}
      </Modal>
      {trainDataset && (
        <TrainModal
          open={Boolean(trainDataset)}
          onClose={() => setTrainDataset(null)}
          copy={copy}
          dataset={trainDataset}
          models={models}
          onPrepared={refetchJobs}
        />
      )}
    </section>
  )
}
