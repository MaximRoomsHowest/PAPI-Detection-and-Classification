import { useCallback, useEffect, useState } from 'react'

/**
 * Minimal data-fetching hook for read-only GET endpoints (e.g. /api/stats,
 * /api/model). Deliberately tiny — react-query would be overkill for a couple
 * of cache-less GETs, and the api.js client already handles timeouts and the
 * `no-store` directive.
 *
 * `fetchFn` should be a function returning a promise (usually one of the
 * api.js helpers). `deps` controls when it re-runs, mirroring useEffect. An
 * `ignore` flag drops stale results if the component unmounts or deps change
 * mid-flight (same pattern as HistoryPage), and `refetch()` forces a re-run.
 *
 * Returns `{ data, loading, error, refetch, setData }`.
 */
export function useFetch(fetchFn, deps = [], options = {}) {
  const { keepPreviousData = false } = options
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const [refreshKey, setRefreshKey] = useState(0)

  // refetch() is an event-handler-style reset (not an effect), so flipping back
  // to loading here is safe and keeps the effect body free of synchronous
  // setState (react-hooks/set-state-in-effect).
  const refetch = useCallback(() => {
    setState((current) => ({
      data: keepPreviousData ? current.data : null,
      loading: true,
      error: null,
    }))
    setRefreshKey((key) => key + 1)
  }, [keepPreviousData])

  const setData = useCallback((valueOrUpdater) => {
    setState((current) => ({
      ...current,
      data: typeof valueOrUpdater === 'function' ? valueOrUpdater(current.data) : valueOrUpdater,
      error: null,
    }))
  }, [])

  useEffect(() => {
    let ignore = false

    Promise.resolve()
      .then(() => fetchFn())
      .then((data) => {
        if (!ignore) {
          setState({ data, loading: false, error: null })
        }
      })
      .catch((error) => {
        if (!ignore) {
          setState((current) => ({
            data: keepPreviousData ? current.data : null,
            loading: false,
            error,
          }))
        }
      })

    return () => {
      ignore = true
    }
    // `deps` is the caller's explicit dependency contract; `fetchFn` is assumed
    // stable (defined at module scope or wrapped). refreshKey drives refetch().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, refreshKey, keepPreviousData])

  return { ...state, refetch, setData }
}
