import { useCallback } from 'react'
import {
  deleteDataset,
  fetchDatasets,
  startAssistedLabeling,
  uploadDatasetBundle,
} from '../lib/api'
import { useFetch } from './useFetch'

export function useDatasets() {
  const { data, loading, error, refetch } = useFetch(fetchDatasets, [], { keepPreviousData: true })
  const datasets = data ?? []

  const uploadBundle = useCallback(
    async (payload) => {
      const dataset = await uploadDatasetBundle(payload)
      refetch()
      return dataset
    },
    [refetch],
  )

  const startAssisted = useCallback(
    async (payload) => {
      const result = await startAssistedLabeling(payload)
      refetch()
      return result
    },
    [refetch],
  )

  const remove = useCallback(
    async (datasetId) => {
      await deleteDataset(datasetId)
      refetch()
    },
    [refetch],
  )

  return { datasets, loading, error, refetch, uploadBundle, startAssisted, remove }
}
