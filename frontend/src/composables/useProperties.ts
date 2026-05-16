import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { extractErrorMessage, propertiesApi, type PropertiesPayload } from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['server', 'properties'] as const

export function useProperties() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: propertiesApi.get,
    staleTime: 30_000,
  })
}

export function useSaveProperties() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => propertiesApi.save(values),
    onSuccess: (data: PropertiesPayload) => {
      qc.setQueryData(QUERY_KEY, data)
      toast.success(t('settings.saved'))
    },
    onError: async (err) => {
      toast.error(t('settings.saveFailed'), { description: await extractErrorMessage(err) })
    },
  })
}
