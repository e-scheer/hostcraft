import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { extractErrorMessage, iconApi } from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['server', 'icon'] as const

export function useServerIcon() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: iconApi.get,
    staleTime: 30_000,
  })
}

export function useApplyPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => iconApi.applyPreset(id),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data)
      toast.success(t('icon.toasts.applied'))
    },
    onError: async (err) => {
      toast.error(t('icon.toasts.applyFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useUploadIcon() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => iconApi.upload(file),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data)
      toast.success(t('icon.toasts.uploaded'))
    },
    onError: async (err) => {
      toast.error(t('icon.toasts.uploadFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useRemoveIcon() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => iconApi.remove(),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data)
      toast.success(t('icon.toasts.reset'))
    },
    onError: async (err) => {
      toast.error(t('icon.toasts.resetFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}
