import { XCircle } from 'lucide-react'

const ACTIVE_STATUSES = new Set(['queued', 'running'])

// Shared background-job list with live progress, used on the Models (evaluate) and
// Datasets (labeling + training) pages. Driven by the polling useJobs hook.
export function JobMonitor({ jobs, onCancel, copy, kinds }) {
  const filtered = kinds ? jobs.filter((job) => kinds.includes(job.kind)) : jobs
  if (!filtered.length) {
    return null
  }
  return (
    <section className="viz-card job-monitor" aria-label={copy.jobs.title}>
      <h3 className="viz-heading">{copy.jobs.title}</h3>
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
              {active && (
                <button className="ghost-button job-cancel" type="button" onClick={() => onCancel(job.id)}>
                  <XCircle size={14} aria-hidden="true" /> {copy.jobs.cancel}
                </button>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
