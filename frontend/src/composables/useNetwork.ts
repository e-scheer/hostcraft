import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  extractErrorMessage,
  networkApi,
  type AllocationPayload,
  type NetworkProfilePatch,
  type Allocation,
} from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['network'] as const

export function useNetwork() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: networkApi.get,
    staleTime: 30_000,
  })
}

export function useUpdateProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: NetworkProfilePatch) => networkApi.update(data),
    onSuccess: (data) => {
      qc.setQueryData(QUERY_KEY, data)
      toast.success(t('network.toasts.saved'))
    },
    onError: async (err) => {
      toast.error(t('network.toasts.saveFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })
}

export function useRefreshIp() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => networkApi.refreshIp(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEY })
    },
  })
}

export function useAllocationActions() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: QUERY_KEY })

  const create = useMutation({
    mutationFn: (data: AllocationPayload) => networkApi.createAllocation(data),
    onSuccess: () => {
      refresh()
      toast.success(t('network.toasts.allocationCreated'))
    },
    onError: async (err) => {
      toast.error(t('network.toasts.allocationFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const update = useMutation({
    mutationFn: (args: { id: number; data: Partial<AllocationPayload> }) =>
      networkApi.updateAllocation(args.id, args.data),
    onSuccess: () => refresh(),
    onError: async (err) => {
      toast.error(t('network.toasts.allocationFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const remove = useMutation({
    mutationFn: (alloc: Allocation) =>
      networkApi.removeAllocation(alloc.id).then(() => alloc),
    onSuccess: (alloc) => {
      refresh()
      toast.success(t('network.toasts.allocationRemoved', { name: alloc.label }))
    },
    onError: async (err) => {
      toast.error(t('network.toasts.allocationFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  return { create, update, remove }
}

const AGENT_KEY = ['network', 'playit', 'agent'] as const

export function usePlayitAgent() {
  return useQuery({
    queryKey: AGENT_KEY,
    queryFn: networkApi.playitAgent,
    // Poll while the agent is starting up so the user gets quick state
    // transitions (created → running). Idle once we settle.
    refetchInterval: (q) => {
      const s = q.state.data?.state
      return s === 'created' || s === 'restarting' ? 2_000 : false
    },
    staleTime: 5_000,
  })
}

export function usePlayitAgentActions() {
  const qc = useQueryClient()

  const start = useMutation({
    mutationFn: (secret?: string) => networkApi.playitAgentStart(secret),
    onSuccess: (data) => {
      qc.setQueryData(AGENT_KEY, data)
      toast.success(t('network.playit.agent.started'))
    },
    onError: async (err) => {
      toast.error(t('network.playit.agent.startFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const stop = useMutation({
    mutationFn: () => networkApi.playitAgentStop(),
    onSuccess: (data) => {
      qc.setQueryData(AGENT_KEY, data)
      toast.success(t('network.playit.agent.stopped'))
    },
    onError: async (err) => {
      toast.error(t('network.playit.agent.stopFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  const refresh = useMutation({
    mutationFn: () => networkApi.playitAgentRefresh(),
    onSuccess: (data) => {
      qc.setQueryData(AGENT_KEY, data)
    },
    onError: async (err) => {
      toast.error(t('network.playit.agent.refreshFailed'), {
        description: await extractErrorMessage(err),
      })
    },
  })

  return { start, stop, refresh }
}

export function usePlayitAgentLogs(enabled: () => boolean) {
  return useQuery({
    queryKey: ['network', 'playit', 'agent', 'logs'] as const,
    queryFn: () => networkApi.playitAgentLogs(200),
    enabled,
    refetchInterval: 5_000,
    staleTime: 0,
  })
}
