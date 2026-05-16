import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { extractErrorMessage, watchdogApi, type WatchdogConfig } from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['server', 'watchdog'] as const

export function useWatchdog() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: watchdogApi.get,
    staleTime: 60_000,
  })
}

export function useUpdateWatchdog() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<WatchdogConfig>) => watchdogApi.update(data),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data)
      toast.success(t('watchdog.saved'))
    },
    onError: async (err) => {
      toast.error(t('watchdog.saveFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}
