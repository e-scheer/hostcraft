import { useQuery } from '@tanstack/vue-query'
import { auditApi, type AuditQuery } from '@/lib/api'

export function useRecentActivity(limit = 8) {
  return useQuery({
    queryKey: ['audit', 'recent', limit] as const,
    queryFn: () => auditApi.list({ limit }).then((r) => r.entries),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })
}

/** Filterable activity feed — for a future /activity page. */
export function useActivity(query: () => AuditQuery) {
  return useQuery({
    queryKey: ['audit', 'list', query] as const,
    queryFn: () => auditApi.list(query()).then((r) => r.entries),
    refetchInterval: 15_000,
    staleTime: 5_000,
  })
}
