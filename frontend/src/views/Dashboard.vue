<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { toast } from 'vue-sonner'
import {
  AlertTriangle,
  Box,
  Check,
  Copy,
  Cpu,
  Gauge,
  Globe,
  MemoryStick,
  Power,
  RotateCcw,
  ShieldCheck,
  Skull,
  Users,
} from 'lucide-vue-next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useServerActions, useServerView } from '@/composables/useServer'
import { useRuntime } from '@/composables/useRuntime'
import { useProperties } from '@/composables/useProperties'
import { useRealtime } from '@/composables/useRealtime'
import { useServerIcon } from '@/composables/useServerIcon'
import { useModTarget } from '@/composables/useMods'
import { useNetwork, usePlayitAgent } from '@/composables/useNetwork'
import { iconApi } from '@/lib/api'
import RecentActivityCard from '@/components/RecentActivityCard.vue'
import PerformanceChart from '@/components/PerformanceChart.vue'

const { t } = useI18n()
const { status, label, dotClass, isBusy, isRunning } = useServerView()
const { start, stop, restart } = useServerActions()
const runtimeQuery = useRuntime()
const propsQuery = useProperties()
const realtime = useRealtime()
const iconQuery = useServerIcon()
const modTarget = useModTarget()
const networkQuery = useNetwork()
const playitAgent = usePlayitAgent()

// Public access health summary — what's the externally-reachable address
// for this server and is the chosen mode wired up correctly?
interface PublicAccess {
  status: 'ok' | 'warn' | 'off'  // ok = ready, warn = misconfigured, off = LAN only
  address: string                 // human-readable address users connect to
  detail: string                  // localised key for the secondary line
}

const publicAccess = computed<PublicAccess>(() => {
  const profile = networkQuery.data.value?.profile
  const pubIp = networkQuery.data.value?.public_ip
  const port = networkQuery.data.value?.primary_port ?? 25565
  const domain = profile?.custom_domain?.trim()

  if (!profile) {
    return { status: 'warn', address: '—', detail: 'dashboard.publicAccess.loading' }
  }

  // Custom domain trumps the mode-specific address — it's what the user
  // wants people to connect to.
  if (domain) {
    return {
      status: 'ok',
      address: port === 25565 ? domain : `${domain}:${port}`,
      detail: 'dashboard.publicAccess.viaDomain',
    }
  }

  if (profile.mode === 'direct') {
    if (!pubIp) {
      return { status: 'warn', address: '—', detail: 'dashboard.publicAccess.noPublicIp' }
    }
    return {
      status: 'ok',
      address: `${pubIp}:${port}`,
      detail: 'dashboard.publicAccess.viaDirect',
    }
  }

  // Both playit modes resolve to the same hostname — only the lifecycle
  // differs (user-managed agent vs panel-managed sidecar).
  const host = profile.playit_hostname.trim()
  if (!host) {
    return { status: 'warn', address: '—', detail: 'dashboard.publicAccess.noPlayitHost' }
  }

  if (profile.mode === 'playit_managed') {
    const agent = playitAgent.data.value
    if (!agent || agent.state !== 'running') {
      return {
        status: 'warn',
        address: host,
        detail: 'dashboard.publicAccess.agentNotRunning',
      }
    }
    if (agent.playit_setup === 'no_tunnel') {
      return {
        status: 'warn',
        address: host,
        detail: 'dashboard.publicAccess.noTunnel',
      }
    }
  }
  return { status: 'ok', address: host, detail: 'dashboard.publicAccess.viaPlayit' }
})

const publicAddressCopied = ref(false)
async function copyPublicAddress() {
  const text = publicAccess.value.address
  if (!text || text === '—') return
  try {
    await navigator.clipboard.writeText(text)
    publicAddressCopied.value = true
    toast.success(t('dashboard.publicAccess.copied'))
    setTimeout(() => { publicAddressCopied.value = false }, 1500)
  } catch {
    toast.error(t('dashboard.quickInfo.copyFailed'))
  }
}

const iconUrl = computed(() => {
  const data = iconQuery.data.value
  return data?.current.present ? iconApi.rawUrl(data.current.etag) : null
})

const loadingStats = computed(
  () => realtime.isPending.value && !realtime.data.value,
)

// ---------------------------------------------------------------------------
// Header subtitle
// ---------------------------------------------------------------------------

const subtitle = computed(() => {
  const data = status.data.value
  if (status.isError.value) return t('dashboard.panelUnreachable')
  if (status.isPending.value && !data) return t('dashboard.loadingStatus')
  if (data?.error) return data.error
  if (data?.uptime_seconds != null) {
    const s = data.uptime_seconds
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const uptime = t('common.uptime', { h, m })
    return `${uptime} · ${data.image || t('common.unknown').toLowerCase()}`
  }
  if (data?.state === 'absent') return t('dashboard.containerAbsent')
  return data?.image || ''
})

// ---------------------------------------------------------------------------
// Stat cards (CPU/RAM/TPS still placeholders pending stats stream)
// ---------------------------------------------------------------------------

interface StatCard {
  labelKey: string
  value: string
  /** Show a subtle hint under the value when present (e.g. "of 42 max"). */
  hint?: string
  icon: typeof Cpu
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  const units = ['KiB', 'MiB', 'GiB', 'TiB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(1)} ${units[i]}`
}

const stats = computed<StatCard[]>(() => {
  const rt = realtime.data.value
  const cfgMax = propsQuery.data.value?.values?.['max-players']
  const max = rt?.players_max ?? cfgMax

  // Players online
  let playersValue = '—'
  if (rt?.players_online != null && max != null) {
    playersValue = `${rt.players_online} / ${max}`
  } else if (max != null) {
    playersValue = `— / ${max}`
  }

  // TPS — show 1m only as the headline
  const tpsValue = rt?.tps ? rt.tps[0].toFixed(1) : '—'

  // CPU
  const cpuValue = rt?.cpu_percent != null ? `${rt.cpu_percent.toFixed(1)} %` : '—'

  // Memory
  let memValue = '—'
  let memHint: string | undefined
  if (rt?.memory_used != null) {
    memValue = fmtBytes(rt.memory_used)
    if (rt.memory_limit && rt.memory_limit > 0) {
      const pct = (rt.memory_used / rt.memory_limit) * 100
      memHint = `${pct.toFixed(0)} % of ${fmtBytes(rt.memory_limit)}`
    }
  }

  return [
    { labelKey: 'dashboard.stats.playersOnline', value: playersValue, icon: Users },
    {
      labelKey: 'dashboard.stats.tps',
      value: tpsValue,
      hint: rt?.tps ? `${rt.tps[1].toFixed(1)} (5m) · ${rt.tps[2].toFixed(1)} (15m)` : undefined,
      icon: Gauge,
    },
    { labelKey: 'dashboard.stats.cpu', value: cpuValue, icon: Cpu },
    { labelKey: 'dashboard.stats.memory', value: memValue, hint: memHint, icon: MemoryStick },
  ]
})

// ---------------------------------------------------------------------------
// Quick info — derived from runtime + server.properties (no hardcoded values)
// ---------------------------------------------------------------------------

const loaderLabel = computed(() => {
  const v = runtimeQuery.data.value?.values?.TYPE
  if (!v) return '—'
  return v.charAt(0) + v.slice(1).toLowerCase()
})

const versionLabel = computed(() => runtimeQuery.data.value?.values?.VERSION || '—')

// Resolved MC version when configured as LATEST/SNAPSHOT, via Mojang manifest.
const mcVersionLabel = computed(() => modTarget.data.value?.mc_version || '')
const mcVersionAlias = computed(() => modTarget.data.value?.mc_version_alias || '')

const addressLabel = computed(() => {
  const port = propsQuery.data.value?.values?.['server-port'] ?? '25565'
  const ip = (propsQuery.data.value?.values?.['server-ip'] as string) || ''
  return `${ip || 'localhost'}:${port}`
})

const difficultyLabel = computed(() => {
  const v = propsQuery.data.value?.values?.difficulty as string | undefined
  if (!v) return '—'
  return v.charAt(0).toUpperCase() + v.slice(1)
})

const whitelistLabel = computed(() => {
  const on = propsQuery.data.value?.values?.['white-list']
  if (on === undefined) return '—'
  return on ? t('dashboard.quickInfo.on') : t('dashboard.quickInfo.off')
})

const motd = computed(() => {
  return (propsQuery.data.value?.values?.motd as string) || '—'
})

const addressCopied = ref(false)
async function copyAddress() {
  const text = addressLabel.value
  if (!text || text === '—') return
  try {
    await navigator.clipboard.writeText(text)
    addressCopied.value = true
    toast.success(t('dashboard.quickInfo.addressCopied'))
    setTimeout(() => { addressCopied.value = false }, 1500)
  } catch {
    toast.error(t('dashboard.quickInfo.copyFailed'))
  }
}
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div class="flex items-center gap-3 min-w-0">
        <RouterLink
          v-if="iconUrl"
          to="/settings"
          class="size-12 rounded-lg overflow-hidden border border-border shadow-sm shrink-0 hover:ring-2 hover:ring-brand-500/50 transition-all"
          :title="t('icon.editTooltip')"
        >
          <img
            :src="iconUrl"
            :alt="t('icon.currentAlt')"
            class="size-full object-cover [image-rendering:pixelated]"
          >
        </RouterLink>
        <div class="space-y-1 min-w-0">
          <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-3">
            {{ t('dashboard.title') }}
            <span class="status-pill status-pill--idle">
              <span
                class="dot"
                :class="dotClass"
              />
              {{ label }}
            </span>
          </h2>
          <p class="text-sm text-muted-foreground">
            {{ subtitle }}
          </p>
        </div>
      </div>
      <div class="flex gap-2">
        <Button
          variant="outline"
          :disabled="isBusy || !isRunning"
          @click="restart.mutate()"
        >
          <RotateCcw />
          {{ t('server.actions.restart') }}
        </Button>
        <Button
          v-if="isRunning"
          variant="destructive"
          :disabled="isBusy"
          @click="stop.mutate()"
        >
          <Power />
          {{ t('server.actions.stop') }}
        </Button>
        <Button
          v-else
          :disabled="isBusy"
          @click="start.mutate()"
        >
          <Power />
          {{ t('server.actions.start') }}
        </Button>
      </div>
    </header>

    <!-- Crash-loop banner — Docker bounced the container 3+ times in a
         row and uptime stays under a minute. Usually triggered by an
         engine swap that left an incompatible world or mods on disk. -->
    <RouterLink
      v-if="status.data.value?.crash_looping"
      to="/runtime"
      class="block rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm hover:bg-destructive/15 transition-colors"
    >
      <div class="flex items-start gap-3">
        <AlertTriangle
          class="text-destructive shrink-0 mt-0.5"
          :size="20"
        />
        <div class="flex-1 min-w-0">
          <div class="font-medium text-foreground">
            {{ t('dashboard.crashLoop.title') }}
          </div>
          <p class="text-muted-foreground leading-relaxed mt-0.5">
            {{ t('dashboard.crashLoop.body', {
              n: status.data.value.restart_count,
              code: status.data.value.last_exit_code ?? '?',
            }) }}
          </p>
          <div class="text-xs text-brand-500 mt-2 font-medium">
            {{ t('dashboard.crashLoop.cta') }}
          </div>
        </div>
      </div>
    </RouterLink>

    <!-- Stat cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card
        v-for="s in stats"
        :key="s.labelKey"
        class="overflow-hidden"
      >
        <CardContent class="p-5">
          <div class="flex items-center justify-between">
            <span class="text-xs uppercase tracking-wider text-muted-foreground font-medium">
              {{ t(s.labelKey) }}
            </span>
            <component
              :is="s.icon"
              :size="16"
              class="text-brand-500"
            />
          </div>
          <div
            v-if="loadingStats && s.value === '—'"
            class="mt-2 h-8 w-28 rounded-md bg-muted animate-pulse"
          />
          <div
            v-else
            class="mt-2 text-2xl font-semibold tracking-tight nums"
          >
            {{ s.value }}
          </div>
          <div
            v-if="s.hint"
            class="mt-0.5 text-xs text-muted-foreground"
          >
            {{ s.hint }}
          </div>
          <div
            v-else-if="loadingStats && s.value === '—'"
            class="mt-0.5 h-3 w-16 rounded bg-muted animate-pulse"
          />
        </CardContent>
      </Card>
    </div>

    <!-- Performance + Quick info -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card class="lg:col-span-2">
        <CardHeader>
          <CardTitle>{{ t('dashboard.performance.title') }}</CardTitle>
          <CardDescription>{{ t('dashboard.performance.subtitle') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <PerformanceChart />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('dashboard.quickInfo.title') }}</CardTitle>
          <CardDescription>{{ t('dashboard.quickInfo.subtitle') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-2.5 text-sm">
          <RouterLink
            to="/runtime"
            class="flex items-center gap-3 py-1 rounded-md hover:bg-accent/40 transition-colors"
          >
            <Box
              :size="16"
              class="text-muted-foreground"
            />
            <span class="text-muted-foreground">{{ t('dashboard.quickInfo.loader') }}</span>
            <span class="ml-auto font-medium">
              {{ loaderLabel }}
              <span class="text-muted-foreground font-normal ml-1">{{ versionLabel }}</span>
            </span>
          </RouterLink>

          <RouterLink
            v-if="mcVersionLabel"
            to="/runtime"
            class="flex items-center gap-3 py-1 rounded-md hover:bg-accent/40 transition-colors"
            :title="
              mcVersionAlias
                ? t('dashboard.quickInfo.mcVersionResolved', {
                  alias: mcVersionAlias,
                  resolved: mcVersionLabel,
                })
                : ''
            "
          >
            <Cpu
              :size="16"
              class="text-muted-foreground"
            />
            <span class="text-muted-foreground">{{ t('dashboard.quickInfo.mcVersion') }}</span>
            <span class="ml-auto font-medium font-mono text-xs">
              {{ mcVersionLabel }}
              <span
                v-if="mcVersionAlias"
                class="text-muted-foreground/70 font-normal ml-1"
              >
                ({{ mcVersionAlias }})
              </span>
            </span>
          </RouterLink>

          <button
            type="button"
            class="group w-full flex items-center gap-3 py-1 rounded-md hover:bg-accent/40 transition-colors text-left"
            :title="t('dashboard.quickInfo.copyAddress')"
            @click="copyAddress"
          >
            <Globe
              :size="16"
              class="text-muted-foreground"
            />
            <span class="text-muted-foreground">{{ t('dashboard.quickInfo.address') }}</span>
            <span class="ml-auto inline-flex items-center gap-1.5 font-medium font-mono text-xs">
              {{ addressLabel }}
              <Check
                v-if="addressCopied"
                :size="12"
                class="text-brand-500 shrink-0"
              />
              <Copy
                v-else
                :size="12"
                class="text-muted-foreground/60 group-hover:text-foreground transition-colors shrink-0"
              />
            </span>
          </button>

          <!-- Public access — operational status of the externally-
               reachable address (direct port-forward / Playit / custom
               domain). Click to copy, or follow to /network to fix. -->
          <RouterLink
            to="/network"
            class="group flex items-start gap-3 py-1 rounded-md hover:bg-accent/40 transition-colors"
            :title="t('dashboard.publicAccess.copyHint')"
            @click.prevent="copyPublicAddress"
          >
            <span class="mt-1.5">
              <span
                class="block size-2 rounded-full"
                :class="
                  publicAccess.status === 'ok'
                    ? 'bg-emerald-500'
                    : publicAccess.status === 'warn'
                      ? 'bg-amber-500'
                      : 'bg-muted-foreground/40'
                "
              />
            </span>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-muted-foreground">{{ t('dashboard.publicAccess.label') }}</span>
                <span
                  class="text-[10px] uppercase tracking-wider font-medium"
                  :class="
                    publicAccess.status === 'ok'
                      ? 'text-emerald-500'
                      : publicAccess.status === 'warn'
                        ? 'text-amber-500'
                        : 'text-muted-foreground'
                  "
                >
                  {{ t(`dashboard.publicAccess.status.${publicAccess.status}`) }}
                </span>
                <span class="ml-auto inline-flex items-center gap-1.5 font-medium font-mono text-xs truncate max-w-[16rem]">
                  {{ publicAccess.address }}
                  <Check
                    v-if="publicAddressCopied"
                    :size="12"
                    class="text-brand-500 shrink-0"
                  />
                  <Copy
                    v-else-if="publicAccess.address !== '—'"
                    :size="12"
                    class="text-muted-foreground/60 group-hover:text-foreground transition-colors shrink-0"
                  />
                </span>
              </div>
              <div class="text-[11px] text-muted-foreground/80 mt-0.5">
                {{ t(publicAccess.detail) }}
              </div>
            </div>
          </RouterLink>

          <RouterLink
            to="/settings"
            class="flex items-center gap-3 py-1 rounded-md hover:bg-accent/40 transition-colors"
          >
            <Skull
              :size="16"
              class="text-muted-foreground"
            />
            <span class="text-muted-foreground">{{ t('dashboard.quickInfo.difficulty') }}</span>
            <span class="ml-auto font-medium">{{ difficultyLabel }}</span>
          </RouterLink>

          <RouterLink
            to="/players"
            class="flex items-center gap-3 py-1 rounded-md hover:bg-accent/40 transition-colors"
          >
            <ShieldCheck
              :size="16"
              class="text-muted-foreground"
            />
            <span class="text-muted-foreground">{{ t('dashboard.quickInfo.whitelist') }}</span>
            <span class="ml-auto font-medium">{{ whitelistLabel }}</span>
          </RouterLink>

          <div class="pt-2 mt-2 border-t border-border">
            <div class="text-[10px] uppercase tracking-wider text-muted-foreground/70 mb-1">
              {{ t('dashboard.quickInfo.motd') }}
            </div>
            <div class="text-xs italic text-muted-foreground line-clamp-2">
              {{ motd }}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Recent activity (full width below) -->
    <RecentActivityCard />
  </div>
</template>
