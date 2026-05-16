import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { realtimeApi, type PerfSample, type PerfWindow } from '@/lib/api'

export interface ChartSample {
  /** Unix ms */
  t: number
  cpu: number | null
  memPct: number | null
  tps: number | null
}

function toChartSample(s: PerfSample): ChartSample {
  return {
    t: new Date(s.t).getTime(),
    cpu: s.cpu_percent,
    memPct:
      s.memory_used != null && s.memory_limit && s.memory_limit > 0
        ? (s.memory_used / s.memory_limit) * 100
        : null,
    tps: s.tps_1m,
  }
}

/**
 * History from the backend's persisted PerfSample table. Survives navigation,
 * reloads, and tab switches — sampled every 30 s in the panel container,
 * retained for 7 days.
 */
export function usePerfHistory(window: () => PerfWindow = () => '1h') {
  const query = useQuery({
    queryKey: ['server', 'perf', 'history', window] as const,
    queryFn: () => realtimeApi.history(window()),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })

  const samples = computed<ChartSample[]>(() => {
    const raw = query.data.value?.samples ?? []
    return raw.map(toChartSample)
  })

  const hasEnough = computed(() => samples.value.length >= 2)
  const isInitialLoading = computed(
    () => query.isPending.value && !query.data.value,
  )

  return { samples, hasEnough, isInitialLoading }
}

/** Pickable window. Bound to the chart's time range selector. */
export const PERF_WINDOWS: PerfWindow[] = ['1h', '6h', '24h', '7d']

export const useChartWindow = () => ref<PerfWindow>('1h')
