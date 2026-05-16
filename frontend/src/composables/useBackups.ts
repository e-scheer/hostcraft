import { computed, type Ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  backupsApi,
  extractErrorMessage,
  type BackupDestination,
  type BackupDestinationPayload,
  type BackupEntry,
  type BackupKind,
} from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['backups', 'list'] as const

/**
 * Live size estimate for each backup kind.
 *
 * If `active` is provided, the query is enabled only while it's true and polls
 * every 5s — so when the user opens the create-backup form they see fresh
 * numbers, and they keep ticking up if the world grows in the background.
 * When `active` is omitted, the query runs once and caches for a minute.
 */
export function useBackupSizes(active?: Ref<boolean>) {
  return useQuery({
    queryKey: ['backups', 'sizes'],
    queryFn: backupsApi.sizes,
    enabled: active ?? true,
    staleTime: 0,
    refetchInterval: () => (active?.value ? 5_000 : false),
    refetchOnWindowFocus: true,
  })
}

export function useBackupsList() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => backupsApi.list().then((r) => r.entries),
    // Poll fast while any backup is in flight, slow otherwise.
    refetchInterval: (query) => {
      const data = query.state.data as BackupEntry[] | undefined
      const inFlight = data?.some((b) => b.status === 'pending' || b.status === 'running')
      return inFlight ? 2_000 : 30_000
    },
    staleTime: 1_000,
  })
}

export function useBackupActions() {
  const qc = useQueryClient()

  const create = useMutation({
    mutationFn: (payload: { kind: BackupKind; name?: string }) =>
      backupsApi.create(payload.kind, payload.name),
    onSuccess: (entry) => {
      // Optimistically prepend so the user sees it immediately.
      qc.setQueryData<BackupEntry[]>(QUERY_KEY, (prev) => [entry, ...(prev ?? [])])
      toast.success(t('backups.toasts.queued', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('backups.toasts.queueFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const remove = useMutation({
    mutationFn: (entry: BackupEntry) =>
      backupsApi.remove(entry.id).then(() => entry),
    onSuccess: (entry) => {
      qc.setQueryData<BackupEntry[]>(QUERY_KEY, (prev) =>
        (prev ?? []).filter((b) => b.id !== entry.id),
      )
      toast.success(t('backups.toasts.deleted', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('backups.toasts.deleteFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  return { create, remove }
}

// ---------------------------------------------------------------------------
// Destinations + remote upload
// ---------------------------------------------------------------------------

const DEST_KEY = ['backups', 'destinations'] as const

export function useDestinations() {
  return useQuery({
    queryKey: DEST_KEY,
    queryFn: () => backupsApi.destinations().then((r) => r.entries),
    staleTime: 30_000,
  })
}

export function useDestinationActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: DEST_KEY })

  const create = useMutation({
    mutationFn: (data: BackupDestinationPayload) => backupsApi.createDestination(data),
    onSuccess: (entry) => {
      qc.setQueryData<BackupDestination[]>(DEST_KEY, (prev) => [...(prev ?? []), entry])
      toast.success(t('destinations.toasts.created', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('destinations.toasts.createFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const update = useMutation({
    mutationFn: (args: { id: number; data: BackupDestinationPayload }) =>
      backupsApi.updateDestination(args.id, args.data),
    onSuccess: () => refresh(),
    onError: async (err) => {
      toast.error(t('destinations.toasts.updateFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const remove = useMutation({
    mutationFn: (entry: BackupDestination) =>
      backupsApi.removeDestination(entry.id).then(() => entry),
    onSuccess: (entry) => {
      qc.setQueryData<BackupDestination[]>(DEST_KEY, (prev) =>
        (prev ?? []).filter((d) => d.id !== entry.id),
      )
      toast.success(t('destinations.toasts.deleted', { name: entry.name }))
    },
    onError: async (err) => {
      toast.error(t('destinations.toasts.deleteFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  /**
   * Test connection. Uses a toast.loading lifecycle that flips to success/error
   * with the structured boto error message ("InvalidAccessKeyId: …").
   */
  const test = useMutation({
    mutationFn: (entry: BackupDestination) =>
      backupsApi.testDestination(entry.id).then((r) => ({ ...r, entry })),
    onMutate: (entry) => ({
      toastId: toast.loading(t('destinations.toasts.testing', { name: entry.name })),
    }),
    onSuccess: (data, _entry, ctx) => {
      const id = ctx?.toastId
      if (data.ok) {
        toast.success(t('destinations.toasts.testOk', { name: data.entry.name }), { id })
      } else {
        toast.error(t('destinations.toasts.testFailed', { name: data.entry.name }), {
          id,
          description: data.error ?? '',
        })
      }
    },
    onError: async (err, _entry, ctx) => {
      const id = ctx?.toastId
      toast.error(t('destinations.toasts.testFailed'), {
        id,
        description: await extractErrorMessage(err),
      })
    },
  })

  return { create, update, remove, test }
}

/** Restore a backup — replaces the current world. */
export function useRestoreBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (entry: BackupEntry) =>
      backupsApi.restore(entry.id).then(() => entry),
    onSuccess: (entry) => {
      toast.success(t('backups.toasts.restoreQueued', { name: entry.name }))
      qc.setQueryData<BackupEntry[]>(['backups', 'list'], (prev) =>
        (prev ?? []).map((b) =>
          b.id === entry.id ? { ...b, restore_status: 'running' } : b,
        ),
      )
      // Bump server status so the sidebar dot reflects the upcoming restart.
      qc.invalidateQueries({ queryKey: ['server', 'status'] })
      qc.invalidateQueries({ queryKey: ['backups', 'list'] })
    },
    onError: async (err) => {
      toast.error(t('backups.toasts.restoreFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

/** Push an already-ready backup to a remote destination. */
export function useUploadBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { backup: BackupEntry; destination: BackupDestination }) =>
      backupsApi
        .uploadTo(args.backup.id, args.destination.id)
        .then(() => args),
    onSuccess: ({ backup, destination }) => {
      toast.success(t('backups.toasts.uploadQueued', { name: backup.name, dest: destination.name }))
      // Bump the entry's remote_status optimistically so the badge flips fast.
      qc.setQueryData<BackupEntry[]>(['backups', 'list'], (prev) =>
        (prev ?? []).map((b) =>
          b.id === backup.id
            ? { ...b, remote_status: 'pending', remote_destination_name: destination.name }
            : b,
        ),
      )
      qc.invalidateQueries({ queryKey: ['backups', 'list'] })
    },
    onError: async (err) => {
      toast.error(t('backups.toasts.uploadFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useBackupSummary(entries: () => BackupEntry[] | undefined) {
  return computed(() => {
    const list = entries() ?? []
    return {
      total: list.length,
      ready: list.filter((b) => b.status === 'ready').length,
      inFlight: list.filter((b) => b.status === 'pending' || b.status === 'running').length,
      totalSize: list.reduce((sum, b) => sum + (b.status === 'ready' ? b.size_bytes : 0), 0),
    }
  })
}
