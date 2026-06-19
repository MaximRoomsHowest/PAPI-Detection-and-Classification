import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelJob, clearFinishedJobs, deleteJob, fetchJobs } from '../lib/api'

// Poll the job list while mounted. The backend has no websockets, so the
// management surface polls — matching the topbar's health-poll pattern. A short
// cadence keeps progress bars lively; the page is only mounted in admin mode.
const POLL_MS = 2500

export function useJobs() {
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState(null)
  // Separate from `error` (which the 2.5s poll resets on every success): a failed
  // cancel/dismiss/clear must stay visible until the next successful action, not be
  // wiped by the next poll tick (audit 2026-06-19).
  const [actionError, setActionError] = useState(null)
  const timerRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const data = await fetchJobs({ limit: 50 })
      setJobs(Array.isArray(data) ? data : [])
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [])

  useEffect(() => {
    let active = true
    const tick = async () => {
      await load()
      if (active) {
        timerRef.current = setTimeout(tick, POLL_MS)
      }
    }
    tick()
    return () => {
      active = false
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [load])

  // Cancel/dismiss/clear catch their own failures and surface them via actionError
  // instead of rejecting into the onClick handler (an unhandled rejection with no user
  // feedback — the action looked wired but silently failed). audit 2026-06-19.
  const cancel = useCallback(
    async (jobId) => {
      try {
        await cancelJob(jobId)
        setActionError(null)
      } catch (err) {
        setActionError(err)
        return
      }
      load()
    },
    [load],
  )

  // Dismiss one finished job. Optimistically drop it so the row disappears
  // immediately (the next poll would anyway), then reconcile from the server.
  const dismiss = useCallback(
    async (jobId) => {
      setJobs((current) => current.filter((job) => job.id !== jobId))
      try {
        await deleteJob(jobId)
        setActionError(null)
      } catch (err) {
        setActionError(err)
      } finally {
        load()
      }
    },
    [load],
  )

  // Clear every finished job (optionally scoped to one kind so a page only
  // clears the jobs it shows). Refreshes from the server afterwards.
  const clearFinished = useCallback(
    async (kind) => {
      try {
        await clearFinishedJobs({ kind })
        setActionError(null)
      } catch (err) {
        setActionError(err)
        return
      }
      load()
    },
    [load],
  )

  return { jobs, error, actionError, refetch: load, cancel, dismiss, clearFinished }
}
