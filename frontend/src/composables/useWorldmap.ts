import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { extractErrorMessage, worldmapApi } from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['worldmap'] as const

export function useWorldmap() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: worldmapApi.status,
    staleTime: 10_000,
  })
}

export function useInstallWorldmap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => worldmapApi.install(),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data.status)
      qc.invalidateQueries({ queryKey: ['mods', 'installed'] })
      qc.invalidateQueries({ queryKey: ['network'] })
      qc.invalidateQueries({ queryKey: ['server', 'status'] })
      toast.success(t('world.toasts.installed'), {
        description: t('world.toasts.installedDesc'),
        duration: 5000,
      })
    },
    onError: async (err) => {
      toast.error(t('world.toasts.installFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}
