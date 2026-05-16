import { useQuery } from '@tanstack/vue-query'
import { realtimeApi } from '@/lib/api'

/** Polled CPU / memory / players / TPS snapshot for the Dashboard cards. */
export function useRealtime(intervalMs = 5_000) {
  return useQuery({
    queryKey: ['server', 'realtime'] as const,
    queryFn: realtimeApi.get,
    refetchInterval: intervalMs,
    staleTime: 1_000,
  })
}
