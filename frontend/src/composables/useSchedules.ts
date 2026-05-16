import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  extractErrorMessage,
  schedulesApi,
  type Schedule,
  type SchedulePayload,
} from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['schedules', 'list'] as const

export function useSchedulesList() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => schedulesApi.list().then((r) => r.entries),
    // Poll medium-frequency so users see "running" → "success/failed" lifecycle.
    refetchInterval: 5_000,
    staleTime: 1_000,
  })
}

export function useScheduleActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: QUERY_KEY })

  const create = useMutation({
    mutationFn: (data: SchedulePayload) => schedulesApi.create(data),
    onSuccess: (entry) => {
      qc.setQueryData<Schedule[]>(QUERY_KEY, (prev) => [...(prev ?? []), entry])
      toast.success(t('schedules.toasts.created', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('schedules.toasts.createFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const update = useMutation({
    mutationFn: (args: { id: number; data: Partial<SchedulePayload> }) =>
      schedulesApi.update(args.id, args.data),
    onSuccess: () => refresh(),
    onError: async (err) => {
      toast.error(t('schedules.toasts.updateFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const remove = useMutation({
    mutationFn: (entry: Schedule) =>
      schedulesApi.remove(entry.id).then(() => entry),
    onSuccess: (entry) => {
      qc.setQueryData<Schedule[]>(QUERY_KEY, (prev) =>
        (prev ?? []).filter((s) => s.id !== entry.id),
      )
      toast.success(t('schedules.toasts.deleted', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('schedules.toasts.deleteFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const runNow = useMutation({
    mutationFn: (entry: Schedule) =>
      schedulesApi.runNow(entry.id).then(() => entry),
    onSuccess: (entry) => {
      toast.success(t('schedules.toasts.queued', { name: entry.name }))
      // Optimistically flip last_status to running.
      qc.setQueryData<Schedule[]>(QUERY_KEY, (prev) =>
        (prev ?? []).map((s) =>
          s.id === entry.id ? { ...s, last_status: 'running' } : s,
        ),
      )
      refresh()
    },
    onError: async (err) => {
      toast.error(t('schedules.toasts.runFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  return { create, update, remove, runNow, refresh }
}

export const CRON_PRESETS: { label: string; cron: string }[] = [
  { label: 'Every 15 min', cron: '*/15 * * * *' },
  { label: 'Every hour', cron: '0 * * * *' },
  { label: 'Daily 4am', cron: '0 4 * * *' },
  { label: 'Daily midnight', cron: '0 0 * * *' },
  { label: 'Weekly Sunday 4am', cron: '0 4 * * 0' },
]
