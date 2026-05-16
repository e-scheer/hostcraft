import { computed } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { extractErrorMessage, serverApi, type ServerState, type ServerStatus } from '@/lib/api'
import { i18n } from '@/i18n'

const t = (key: string, params?: Record<string, unknown>) =>
  i18n.global.t(key, params ?? {}) as string

const QUERY_KEY = ['server', 'status'] as const

export function useServerStatus() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: serverApi.status,
    refetchInterval: 3_000,
    staleTime: 0,
  })
}

export function useServerActions() {
  const qc = useQueryClient()

  const refresh = () => qc.invalidateQueries({ queryKey: QUERY_KEY })
  const setOptimistic = (state: ServerState) => {
    qc.setQueryData<ServerStatus>(QUERY_KEY, (prev) =>
      prev
        ? { ...prev, state }
        : { state, started_at: null, image: '', health: null, uptime_seconds: null, error: null },
    )
  }

  const start = useMutation({
    mutationFn: () => serverApi.start(),
    onMutate: () => setOptimistic('restarting'),
    onSuccess: () => {
      toast.success(t('server.toasts.starting'))
      refresh()
    },
    onError: async (err) => {
      toast.error(t('server.toasts.startFailed'), { description: await extractErrorMessage(err) })
      refresh()
    },
  })

  const stop = useMutation({
    mutationFn: () => serverApi.stop(),
    onMutate: () => setOptimistic('restarting'),
    onSuccess: () => {
      toast.success(t('server.toasts.stopping'))
      refresh()
    },
    onError: async (err) => {
      toast.error(t('server.toasts.stopFailed'), { description: await extractErrorMessage(err) })
      refresh()
    },
  })

  const restart = useMutation({
    mutationFn: () => serverApi.restart(),
    onMutate: () => setOptimistic('restarting'),
    onSuccess: () => {
      toast.success(t('server.toasts.restarting'))
      refresh()
    },
    onError: async (err) => {
      toast.error(t('server.toasts.restartFailed'), { description: await extractErrorMessage(err) })
      refresh()
    },
  })

  return { start, stop, restart }
}

export function useServerView() {
  const status = useServerStatus()

  const state = computed<ServerState>(() => status.data.value?.state ?? 'unknown')

  const health = computed(() => status.data.value?.health ?? null)
  // MC inside the container can still be booting even though Docker says
  // "running" — itzg's healthcheck reports "starting" until MC is actually up.
  const isBooting = computed(() => state.value === 'running' && health.value === 'starting')

  const label = computed(() => {
    if (isBooting.value) return t('server.states.booting')
    switch (state.value) {
      case 'running': return t('server.states.running')
      case 'exited':
      case 'created': return t('server.states.stopped')
      case 'restarting': return t('server.states.working')
      case 'paused': return t('server.states.paused')
      case 'absent': return t('server.states.absent')
      case 'error': return t('server.states.unreachable')
      default: return t('server.states.unknown')
    }
  })

  const dotClass = computed(() => {
    if (isBooting.value) return 'bg-amber-400 animate-pulse'
    switch (state.value) {
      case 'running':
        return 'bg-brand-500 shadow-[0_0_10px_var(--brand-500)]'
      case 'restarting':
        return 'bg-amber-400 animate-pulse'
      case 'error':
        return 'bg-destructive'
      case 'paused':
        return 'bg-amber-400'
      default:
        return 'bg-muted-foreground/60'
    }
  })

  const isBusy = computed(() => state.value === 'restarting' || isBooting.value)
  const isRunning = computed(() => state.value === 'running' && !isBooting.value)

  return { status, state, label, dotClass, isBusy, isRunning, isBooting }
}
