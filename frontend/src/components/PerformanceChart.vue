<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { VisXYContainer, VisLine, VisAxis, VisCrosshair } from '@unovis/vue'
import {
  PERF_WINDOWS,
  useChartWindow,
  usePerfHistory,
  type ChartSample,
} from '@/composables/usePerfHistory'

const { t } = useI18n()
const window = useChartWindow()
const { samples, hasEnough, isInitialLoading } = usePerfHistory(() => window.value)

// All 3 series share a single Y axis (0-100). TPS (0-20) is normalised to %.
const x = (s: ChartSample) => s.t
const yCpu = (s: ChartSample) => s.cpu
const yMem = (s: ChartSample) => s.memPct
const yTps = (s: ChartSample) => (s.tps != null ? (s.tps / 20) * 100 : null)

const xTickFormat = (ms: number) => {
  const d = new Date(ms)
  const hh = d.getHours().toString().padStart(2, '0')
  const mm = d.getMinutes().toString().padStart(2, '0')
  return `${hh}:${mm}`
}
const yTickFormat = (n: number) => `${Math.round(n)}%`

// Brand-aligned palette.
const COLOR_CPU = 'oklch(0.7 0.17 155)'   // emerald (brand-500)
const COLOR_MEM = 'oklch(0.55 0.15 200)'  // teal
const COLOR_TPS = 'oklch(0.78 0.16 80)'   // amber

const tickCount = computed(() => (window.value === '1h' ? 5 : 6))

const crosshairTemplate = (d: ChartSample) => {
  const time = xTickFormat(d.t)
  const cpu = d.cpu != null ? `${d.cpu.toFixed(1)} %` : '—'
  const mem = d.memPct != null ? `${d.memPct.toFixed(1)} %` : '—'
  const tps = d.tps != null ? d.tps.toFixed(1) : '—'
  return `
    <div style="font-family: var(--font-sans); font-size: 11px; padding: 6px 8px; line-height: 1.5; min-width: 130px;">
      <div style="font-weight: 600; opacity: 0.7; margin-bottom: 4px;">${time}</div>
      <div style="display: flex; justify-content: space-between; gap: 12px;"><span><span style="color: ${COLOR_CPU};">●</span> CPU</span><span style="font-variant-numeric: tabular-nums;">${cpu}</span></div>
      <div style="display: flex; justify-content: space-between; gap: 12px;"><span><span style="color: ${COLOR_MEM};">●</span> Memory</span><span style="font-variant-numeric: tabular-nums;">${mem}</span></div>
      <div style="display: flex; justify-content: space-between; gap: 12px;"><span><span style="color: ${COLOR_TPS};">●</span> TPS</span><span style="font-variant-numeric: tabular-nums;">${tps}</span></div>
    </div>
  `
}

function setWindow(w: typeof PERF_WINDOWS[number]) {
  window.value = w
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="inline-flex rounded-md border border-border bg-card p-0.5 gap-0.5">
        <button
          v-for="w in PERF_WINDOWS"
          :key="w"
          type="button"
          class="px-2.5 py-0.5 text-[11px] font-mono rounded text-muted-foreground transition-colors hover:text-foreground"
          :class="window === w ? 'bg-accent text-foreground' : ''"
          @click="setWindow(w)"
        >
          {{ w }}
        </button>
      </div>

      <div class="flex items-center gap-3 text-[11px] text-muted-foreground">
        <span class="inline-flex items-center gap-1.5">
          <span class="size-2 rounded-full" :style="{ background: COLOR_CPU }" /> CPU
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="size-2 rounded-full" :style="{ background: COLOR_MEM }" /> Memory
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="size-2 rounded-full" :style="{ background: COLOR_TPS }" /> TPS
        </span>
      </div>
    </div>

    <div class="relative w-full h-56">
      <div v-if="isInitialLoading" class="absolute inset-0 grid place-items-center">
        <div class="size-8 rounded-full border-2 border-border border-t-brand-500 animate-spin" />
      </div>

      <div
        v-else-if="!hasEnough"
        class="absolute inset-0 grid place-items-center text-center text-xs text-muted-foreground"
      >
        <div class="space-y-1">
          <div>{{ t('dashboard.performance.collecting') }}</div>
          <div class="opacity-60">~30 s / sample</div>
        </div>
      </div>

      <VisXYContainer
        v-else
        :data="samples"
        :height="224"
        :margin="{ top: 8, right: 4, bottom: 24, left: 36 }"
      >
        <VisLine :x="x" :y="yCpu" :color="COLOR_CPU" :line-width="1.5" :curve-type="'monotoneX'" />
        <VisLine :x="x" :y="yMem" :color="COLOR_MEM" :line-width="1.5" :curve-type="'monotoneX'" />
        <VisLine :x="x" :y="yTps" :color="COLOR_TPS" :line-width="1.5" :curve-type="'monotoneX'" />
        <VisAxis
          type="x"
          :tick-format="xTickFormat"
          :num-ticks="tickCount"
          :grid-line="false"
        />
        <VisAxis
          type="y"
          :tick-format="yTickFormat"
          :num-ticks="4"
          :domain="[0, 100]"
          :grid-line="false"
        />
        <VisCrosshair :template="crosshairTemplate" />
      </VisXYContainer>
    </div>
  </div>
</template>
