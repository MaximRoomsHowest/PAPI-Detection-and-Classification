import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelJob, fetchJobs } from '../lib/api'

// Poll the job list while mounted. The backend has no websockets, so the
// management surface polls — matching the topbar's health-poll pattern. A short
// cadence keeps progress bars lively; the page is only mounted in admin mode.
const POLL_MS = 2500

export function useJobs() {
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState(null)
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

  const cancel = useCallback(
    async (jobId) => {
      await cancelJob(jobId)
      load()
    },
    [load],
  )

  return { jobs, error, refetch: load, cancel }
}
