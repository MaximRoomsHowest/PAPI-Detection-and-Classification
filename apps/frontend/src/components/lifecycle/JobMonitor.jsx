import { Trash2, XCircle } from 'lucide-react'

const ACTIVE_STATUSES = new Set(['queued', 'running'])

// Shared background-job list with live progress, used on the Models (evaluate) and
// Datasets (labeling + training) pages. Driven by the polling useJobs hook.
// onCancel/onDismiss/onClearFinished are all optional so a caller can render a
// read-only monitor; each action button is gated on its handler. actionError surfaces
// a failed cancel/dismiss/clear (otherwise a silent no-op).
export function JobMonitor({ jobs, onCancel, onDismiss, onClearFinished, actionError, copy, kinds }) {
  const filtered = kinds ? jobs.filter((job) => kinds.includes(job.kind)) : jobs
  if (!filtered.length) {
    return null
  }
  const finishedCount = filtered.filter((job) => !ACTIVE_STATUSES.has(job.status)).length
  return (
    <section className="viz-card job-monitor" aria-label={copy.jobs.title}>
      <div className="job-monitor__head">
        <h3 className="viz-heading">{copy.jobs.title}</h3>
        {onClearFinished && finishedCount > 0 && (
          <button className="ghost-button job-clear" type="button" onClick={onClearFinished}>
            <Trash2 size={14} aria-hidden="true" />{' '}
            {copy.jobs.clearFinished.replace('{count}', finishedCount)}
          </button>
        )}
      </div>
      {actionError && (
        <p className="job-monitor__error mono" role="alert">
          {copy.jobs.actionFailed}
        </p>
      )}
      <ul className="job-list">
        {filtered.map((job) => {
          const active = ACTIVE_STATUSES.has(job.status)
          const pct = Math.round((job.progress || 0) * 100)
          return (
            <li key={job.id} className={`job-row job-row--${job.status}`}>
              <div className="job-row__head">
                <span className="job-row__kind mono">{copy.jobs.kinds[job.kind] ?? job.kind}</span>
                <span className={`job-status job-status--${job.status}`}>
                  {copy.jobs.status[job.status] ?? job.status}
                </span>
              </div>
              {active && (
                <div
                  className="job-progress"
                  role="progressbar"
                  aria-label={copy.jobs.kinds[job.kind] ?? job.kind}
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <span style={{ width: `${pct}%` }} />
                </div>
              )}
              {(job.phase || job.error) && (
                <p className={`job-row__phase mono${job.error ? ' job-row__phase--error' : ''}`}>
                  {job.error || job.phase}
                </p>
              )}
              {active ? (
                onCancel && (
                  <button className="ghost-button job-cancel" type="button" onClick={() => onCancel(job.id)}>
                    <XCircle size={14} aria-hidden="true" /> {copy.jobs.cancel}
                  </button>
                )
              ) : (
                onDismiss && (
                  <button className="ghost-button job-cancel" type="button" onClick={() => onDismiss(job.id)}>
                    <Trash2 size={14} aria-hidden="true" /> {copy.jobs.dismiss}
                  </button>
                )
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
