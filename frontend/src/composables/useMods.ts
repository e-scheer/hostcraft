import { computed, type Ref } from 'vue'
import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  extractErrorMessage,
  modsApi,
  type ModProvider,
  type ModSearchPayload,
} from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

export function useModTarget() {
  return useQuery({
    queryKey: ['mods', 'target'] as const,
    queryFn: modsApi.target,
    staleTime: 60_000,
  })
}

export function useModSearch(query: Ref<string>, strictVersion: Ref<boolean>) {
  return useQuery<ModSearchPayload>({
    // The query reruns when `query` or `strictVersion` change.
    queryKey: ['mods', 'search', query, strictVersion] as const,
    queryFn: () => modsApi.search(query.value, { strictVersion: strictVersion.value }),
    placeholderData: keepPreviousData,
    enabled: computed(() => query.value.trim().length >= 2),
    staleTime: 60_000,
  })
}

export function useModVersions(provider: Ref<ModProvider | null>, projectId: Ref<string | null>) {
  return useQuery({
    queryKey: ['mods', 'versions', provider, projectId] as const,
    queryFn: () => modsApi.versions(provider.value!, projectId.value!),
    enabled: computed(() => Boolean(provider.value && projectId.value)),
    staleTime: 60_000,
  })
}

export function useInstalledMods() {
  return useQuery({
    queryKey: ['mods', 'installed'] as const,
    queryFn: modsApi.installed,
    staleTime: 30_000,
  })
}

export function useInstallMod() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { provider: ModProvider; project_id: string; version_id?: string }) =>
      modsApi.install(args.provider, args.project_id, args.version_id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['mods', 'installed'] })
      toast.success(t('mods.toasts.installed', { name: res.filename }), {
        description: res.verified
          ? t('mods.toasts.installedVerified')
          : t('mods.toasts.installedUnverified'),
      })
    },
    onError: async (err) => {
      toast.error(t('mods.toasts.installFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useUninstallMod() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => modsApi.uninstall(id),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['mods', 'installed'] })
      toast.success(t('mods.toasts.uninstalled', { name: res.removed }))
    },
    onError: async (err) => {
      toast.error(t('mods.toasts.uninstallFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useInspectUpload() {
  return useMutation({
    mutationFn: (file: File) => modsApi.inspectUpload(file),
    onError: async (err) => {
      toast.error(t('mods.manual.inspectFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useUploadInstall() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: { file: File; force_kind?: 'mod' | 'plugin' }) =>
      modsApi.uploadInstall(args.file, args.force_kind),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['mods', 'installed'] })
      toast.success(t('mods.toasts.installed', { name: res.filename }))
    },
    onError: async (err) => {
      toast.error(t('mods.toasts.installFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}
