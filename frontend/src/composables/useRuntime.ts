import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  backupsApi,
  extractErrorMessage,
  runtimeApi,
  type BackupEntry,
  type ServerStatus,
} from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['server', 'runtime'] as const
const OPTIONS_KEY = ['server', 'runtime', 'options'] as const

export function useRuntime() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: runtimeApi.get,
    staleTime: 5_000,
  })
}

export function useRuntimeOptions() {
  return useQuery({
    queryKey: OPTIONS_KEY,
    queryFn: runtimeApi.options,
    staleTime: 24 * 60 * 60_000, // static-ish list
  })
}

export function useApplyRuntime() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: {
      values: Record<string, string | boolean>
      image_tag?: string
      engine_reset?: boolean
    }) =>
      runtimeApi.apply(args.values, {
        image_tag: args.image_tag,
        engine_reset: args.engine_reset,
      }),
    onMutate: () => {
      qc.setQueryData<ServerStatus>(['server', 'status'], (prev) =>
        prev
          ? { ...prev, state: 'restarting', health: 'starting' }
          : {
              state: 'restarting',
              started_at: null,
              image: '',
              health: 'starting',
              uptime_seconds: null,
              error: null,
            },
      )
      // Visible feedback for the duration of the apply (~5-30 s while
      // Docker stops + recreates the container). The id is forwarded to
      // onSuccess/onError so we can mutate this toast in-place rather
      // than spawn a fresh one.
      const toastId = toast.loading(t('runtime.applying'))
      return { toastId }
    },
    onSuccess: (data, _vars, ctx) => {
      qc.setQueryData(QUERY_KEY, data)
      qc.invalidateQueries({ queryKey: ['server', 'status'] })
      toast.success(t('runtime.applied'), {
        id: ctx?.toastId,
        duration: 3500,
      })
    },
    onError: async (err, _vars, ctx) => {
      qc.invalidateQueries({ queryKey: ['server', 'status'] })
      toast.error(t('runtime.applyFailed'), {
        id: ctx?.toastId,
        description: await extractErrorMessage(err),
      })
    },
  })
}

/**
 * Trigger a synchronous-feeling safety backup before a risky runtime change:
 * create a `full` backup, poll until status is `ready`, resolve.
 *
 * Resolves with the completed Backup. Rejects on backup failure or timeout.
 * The caller surfaces a toast lifecycle.
 */
export async function createSafetyBackup(label: string): Promise<BackupEntry> {
  const created = await backupsApi.create('full', label)

  const TIMEOUT_MS = 15 * 60_000 // 15 min — enough for hundreds of MB
  const POLL_MS = 2_000
  const started = Date.now()

  while (Date.now() - started < TIMEOUT_MS) {
    await new Promise((r) => setTimeout(r, POLL_MS))
    const list = await backupsApi.list()
    const fresh = list.entries.find((b) => b.id === created.id)
    if (!fresh) continue
    if (fresh.status === 'ready') return fresh
    if (fresh.status === 'failed') {
      throw new Error(fresh.error?.split('\n')[0] || 'backup failed')
    }
  }
  throw new Error('backup timed out')
}
