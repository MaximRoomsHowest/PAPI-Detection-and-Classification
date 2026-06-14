import { useCallback } from 'react'
import {
  deleteModel,
  evaluateModel,
  fetchModels,
  promoteModel,
  setModelDisabled,
  uploadModel,
} from '../lib/api'
import { useFetch } from './useFetch'

// Model registry list + mutations, mirroring useRunwayManagement: a useFetch list
// plus thin mutation wrappers that refetch so the UI reflects the new registry.
export function useModelManagement() {
  const { data, loading, error, refetch } = useFetch(fetchModels, [], { keepPreviousData: true })
  const models = data ?? []

  const upload = useCallback(
    async (payload) => {
      const model = await uploadModel(payload)
      refetch()
      return model
    },
    [refetch],
  )

  const promote = useCallback(
    async (modelId) => {
      await promoteModel(modelId)
      refetch()
    },
    [refetch],
  )

  const setDisabled = useCallback(
    async (modelId, disabled) => {
      await setModelDisabled(modelId, disabled)
      refetch()
    },
    [refetch],
  )

  const remove = useCallback(
    async (modelId) => {
      await deleteModel(modelId)
      refetch()
    },
    [refetch],
  )

  const evaluate = useCallback((modelId, body) => evaluateModel(modelId, body), [])

  return { models, loading, error, refetch, upload, promote, setDisabled, remove, evaluate }
}
