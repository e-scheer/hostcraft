import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  extractErrorMessage,
  opsApi,
  whitelistApi,
  type OpEntry,
  type WhitelistEntry,
} from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const WHITELIST_KEY = ['server', 'whitelist'] as const
const OPS_KEY = ['server', 'ops'] as const

// ---------------------------------------------------------------------------
// Whitelist
// ---------------------------------------------------------------------------

export function useWhitelist() {
  return useQuery({
    queryKey: WHITELIST_KEY,
    queryFn: () => whitelistApi.list().then((r) => r.entries),
    staleTime: 30_000,
  })
}

export function useWhitelistActions() {
  const qc = useQueryClient()

  const add = useMutation({
    mutationFn: (name: string) => whitelistApi.add(name),
    onSuccess: ({ entry, entries }) => {
      qc.setQueryData<WhitelistEntry[]>(WHITELIST_KEY, entries)
      toast.success(t('players.toasts.whitelistAdded', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('players.toasts.whitelistAddFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const remove = useMutation({
    mutationFn: (entry: WhitelistEntry) =>
      whitelistApi.remove(entry.uuid).then((r) => ({ entry, entries: r.entries })),
    onSuccess: ({ entry, entries }) => {
      qc.setQueryData<WhitelistEntry[]>(WHITELIST_KEY, entries)
      toast.success(t('players.toasts.whitelistRemoved', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('players.toasts.whitelistRemoveFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  return { add, remove }
}

// ---------------------------------------------------------------------------
// Ops
// ---------------------------------------------------------------------------

export function useOps() {
  return useQuery({
    queryKey: OPS_KEY,
    queryFn: () => opsApi.list().then((r) => r.entries),
    staleTime: 30_000,
  })
}

export function useOpsActions() {
  const qc = useQueryClient()

  const add = useMutation({
    mutationFn: (payload: { name: string; level: number; bypassesPlayerLimit: boolean }) =>
      opsApi.add(payload.name, payload.level, payload.bypassesPlayerLimit),
    onSuccess: ({ entry, entries }) => {
      qc.setQueryData<OpEntry[]>(OPS_KEY, entries)
      toast.success(t('players.toasts.opAdded', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('players.toasts.opAddFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const update = useMutation({
    mutationFn: (payload: { uuid: string; level?: number; bypassesPlayerLimit?: boolean }) =>
      opsApi.update(payload.uuid, {
        level: payload.level,
        bypassesPlayerLimit: payload.bypassesPlayerLimit,
      }),
    onSuccess: ({ entries }) => {
      qc.setQueryData<OpEntry[]>(OPS_KEY, entries)
    },
    onError: async (err) => {
      toast.error(t('players.toasts.opUpdateFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const remove = useMutation({
    mutationFn: (entry: OpEntry) =>
      opsApi.remove(entry.uuid).then((r) => ({ entry, entries: r.entries })),
    onSuccess: ({ entry, entries }) => {
      qc.setQueryData<OpEntry[]>(OPS_KEY, entries)
      toast.success(t('players.toasts.opRemoved', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('players.toasts.opRemoveFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  return { add, update, remove }
}
