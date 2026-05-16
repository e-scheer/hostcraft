import { computed, ref, type Ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { extractErrorMessage, filesApi, type FileEntry } from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

function joinPath(dir: string, name: string): string {
  if (!dir) return name
  return `${dir.replace(/\/+$/, '')}/${name}`
}

export function useFilesListing(path: Ref<string>) {
  return useQuery({
    queryKey: ['files', 'list', path] as const,
    queryFn: () => filesApi.list(path.value),
    staleTime: 2_000,
  })
}

export function useFileActions(currentPath: Ref<string>) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['files', 'list'] })

  const remove = useMutation({
    mutationFn: (paths: string[]) => Promise.all(paths.map((p) => filesApi.delete(p))),
    onSuccess: (_data, paths) => {
      toast.success(
        paths.length === 1
          ? t('files.toasts.fileDeleted')
          : t('files.toasts.itemsDeleted', { n: paths.length }),
      )
      refresh()
    },
    onError: async (err) => {
      toast.error(t('files.toasts.deleteFailed'), { description: await extractErrorMessage(err) })
    },
  })

  const upload = useMutation({
    mutationFn: (files: File[]) => filesApi.upload(currentPath.value, files),
    onSuccess: (data) => {
      const n = data.uploaded.length
      toast.success(
        n === 1
          ? t('files.toasts.uploaded', { name: data.uploaded[0].name })
          : t('files.toasts.uploadedMany', { n }),
      )
      refresh()
    },
    onError: async (err) => {
      toast.error(t('files.toasts.uploadFailed'), { description: await extractErrorMessage(err) })
    },
  })

  const mkdir = useMutation({
    mutationFn: (name: string) => filesApi.mkdir(joinPath(currentPath.value, name)),
    onSuccess: (entry) => {
      toast.success(t('files.toasts.folderCreated', { name: entry.name }))
      refresh()
    },
    onError: async (err) => {
      toast.error(t('files.toasts.folderFailed'), { description: await extractErrorMessage(err) })
    },
  })

  return { remove, upload, mkdir, refresh }
}

export function useFileSelection() {
  const selected = ref<Set<string>>(new Set())

  const has = (name: string) => selected.value.has(name)
  const toggle = (name: string) => {
    const next = new Set(selected.value)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    selected.value = next
  }
  const setAll = (names: string[]) => {
    selected.value = new Set(names)
  }
  const clear = () => {
    selected.value = new Set()
  }
  const count = computed(() => selected.value.size)
  const list = computed(() => Array.from(selected.value))

  return { selected, has, toggle, setAll, clear, count, list }
}

export function entryIcon(entry: FileEntry): 'folder' | 'file' {
  return entry.is_dir ? 'folder' : 'file'
}

export function formatBytes(bytes: number): string {
  if (!bytes) return '—'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatRelativeTime(unix: number): string {
  if (!unix) return ''
  const ms = Date.now() - unix * 1000
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return t('common.justNow')
  if (minutes < 60) return t('common.minutesAgo', { n: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return t('common.hoursAgo', { n: hours })
  const days = Math.floor(hours / 24)
  if (days < 30) return t('common.daysAgo', { n: days })
  return new Date(unix * 1000).toLocaleDateString(i18n.global.locale.value)
}
