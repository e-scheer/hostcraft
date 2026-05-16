<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Cable,
  Check,
  Copy,
  Globe,
  Loader2,
  Play,
  Plus,
  Power,
  RefreshCw,
  Terminal,
  Trash2,
  TriangleAlert,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useAllocationActions,
  useNetwork,
  usePlayitAgent,
  usePlayitAgentActions,
  usePlayitAgentLogs,
  useRefreshIp,
  useUpdateProfile,
} from '@/composables/useNetwork'
import type { Allocation, NetworkMode } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const dialog = useDialogStore()
const network = useNetwork()
const updateProfile = useUpdateProfile()
const refreshIp = useRefreshIp()
const allocations = useAllocationActions()

// ---------------------------------------------------------------------------
// Mode + domain + Playit form (debounced save)
// ---------------------------------------------------------------------------

const localMode = ref<NetworkMode>('direct')
const localDomain = ref('')
const localPlayitHost = ref('')

watch(
  () => network.data.value,
  (data) => {
    if (!data) return
    localMode.value = data.profile.mode
    localDomain.value = data.profile.custom_domain
    localPlayitHost.value = data.profile.playit_hostname
  },
  { immediate: true },
)

function saveProfile() {
  updateProfile.mutate({
    mode: localMode.value,
    custom_domain: localDomain.value.trim(),
    playit_hostname: localPlayitHost.value.trim(),
  })
}

const profileDirty = computed(() => {
  const d = network.data.value?.profile
  if (!d) return false
  return (
    d.mode !== localMode.value ||
    d.custom_domain !== localDomain.value ||
    d.playit_hostname !== localPlayitHost.value
  )
})

// ---------------------------------------------------------------------------
// Copy helper
// ---------------------------------------------------------------------------

const copiedKey = ref<string | null>(null)
async function copyText(text: string, key: string) {
  try {
    await navigator.clipboard.writeText(text)
    copiedKey.value = key
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = null
    }, 1500)
  } catch {
    // fallback noop
  }
}

// ---------------------------------------------------------------------------
// Allocation form
// ---------------------------------------------------------------------------

const allocFormOpen = ref(false)
const allocLabel = ref('')
const allocHostPort = ref<number | ''>('')
const allocContainerPort = ref<number | ''>('')
const allocProto = ref<'tcp' | 'udp'>('tcp')

const ALLOC_PRESETS: { label: string; container_port: number; protocol: 'tcp' | 'udp' }[] = [
  { label: 'BlueMap', container_port: 8100, protocol: 'tcp' },
  { label: 'Dynmap', container_port: 8123, protocol: 'tcp' },
  { label: 'Squaremap', container_port: 8080, protocol: 'tcp' },
  { label: 'Voicechat', container_port: 24454, protocol: 'udp' },
  { label: 'Geyser', container_port: 19132, protocol: 'udp' },
]

function applyPreset(p: typeof ALLOC_PRESETS[number]) {
  allocLabel.value = p.label
  allocContainerPort.value = p.container_port
  allocHostPort.value = allocHostPort.value || p.container_port
  allocProto.value = p.protocol
}

function resetAllocForm() {
  allocLabel.value = ''
  allocHostPort.value = ''
  allocContainerPort.value = ''
  allocProto.value = 'tcp'
}

function onSubmitAllocation() {
  if (!allocLabel.value.trim() || !allocHostPort.value || !allocContainerPort.value) return
  allocations.create.mutate(
    {
      label: allocLabel.value.trim(),
      host_port: Number(allocHostPort.value),
      container_port: Number(allocContainerPort.value),
      protocol: allocProto.value,
    },
    {
      onSuccess: () => {
        allocFormOpen.value = false
        resetAllocForm()
      },
    },
  )
}

async function onDeleteAllocation(alloc: Allocation) {
  const ok = await dialog.confirm({
    title: t('network.allocations.confirmDelete', { name: alloc.label }),
    description: t('network.allocations.confirmDeleteDesc'),
    confirmLabel: t('common.delete'),
    variant: 'destructive',
  })
  if (!ok) return
  allocations.remove.mutate(alloc)
}

// ---------------------------------------------------------------------------
// Computed helpers
// ---------------------------------------------------------------------------

const data = computed(() => network.data.value)
const isPlayitMode = computed(() =>
  localMode.value === 'playit_guided' || localMode.value === 'playit_managed',
)
const isPlayitManaged = computed(() => localMode.value === 'playit_managed')

// --- Playit managed agent ---
const agentQuery = usePlayitAgent()
const agentActions = usePlayitAgentActions()
const showLogs = ref(false)
const agentLogs = usePlayitAgentLogs(() => showLogs.value && isPlayitManaged.value)
const localSecret = ref('')

const agentRunning = computed(() => agentQuery.data.value?.state === 'running')
const agentBusy = computed(() => {
  const s = agentQuery.data.value?.state
  return s === 'created' || s === 'restarting'
})

// When a secret is already on file we hide the password input entirely
// and show a clear "saved" badge + "Replace" button. An empty input with
// a placeholder reads as "type something" — premium UX needs the
// affordance to be unambiguous.
const replacingSecret = ref(false)
const showSecretInput = computed(
  () => !agentQuery.data.value?.has_secret || replacingSecret.value,
)

const detectedHostname = computed(() => agentQuery.data.value?.detected_hostname ?? '')

// Auto-fill the hostname field the first time the agent reports a tunnel,
// so the user doesn't have to copy from the playit.gg dashboard. Only
// fills when the field is empty — never overrides an explicit user value.
watch(detectedHostname, (host) => {
  if (host && !localPlayitHost.value.trim() && isPlayitManaged.value) {
    localPlayitHost.value = host
  }
})

function useDetectedHostname() {
  const host = detectedHostname.value
  if (host) localPlayitHost.value = host
}
function startAgent() {
  // Empty secret → backend reuses the stored one (lets the user click Start
  // again to bounce the agent without re-pasting the key).
  agentActions.start.mutate(localSecret.value.trim() || undefined, {
    onSuccess: () => {
      localSecret.value = ''
      replacingSecret.value = false
    },
  })
}
function stopAgent() { agentActions.stop.mutate() }
function startReplacingSecret() {
  replacingSecret.value = true
  // Focus shifts to the input on next tick by virtue of v-if mounting.
}
function cancelReplacingSecret() {
  replacingSecret.value = false
  localSecret.value = ''
}

function effectivePublicAddress(): string {
  const d = data.value
  if (!d) return '—'
  if (isPlayitMode.value) {
    return d.profile.playit_hostname || t('network.publicAccess.playitNotSet')
  }
  return d.profile.public_ip_override || d.public_ip || '—'
}

const dnsRecordsByType: Record<string, number> = { A: 0, CNAME: 1, SRV: 2, TXT: 3 }
const sortedDnsRecords = computed(() => {
  const records = data.value?.dns_records ?? []
  return [...records].sort(
    (a, b) =>
      (dnsRecordsByType[a.type] ?? 99) - (dnsRecordsByType[b.type] ?? 99),
  )
})
</script>

<template>
  <div class="space-y-6">
    <header class="space-y-1">
      <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <Cable :size="22" class="text-brand-500" />
        {{ t('network.title') }}
      </h2>
      <p class="text-sm text-muted-foreground">{{ t('network.subtitle') }}</p>
    </header>

    <div
      v-if="network.isPending.value && !network.data.value"
      class="flex items-center gap-2 text-muted-foreground text-sm"
    >
      <Loader2 class="animate-spin" :size="14" />
      {{ t('common.loading') }}
    </div>

    <template v-else-if="data">
      <!-- ============================================================ -->
      <!-- Public access                                                 -->
      <!-- ============================================================ -->
      <Card>
        <CardHeader class="flex flex-row items-center justify-between gap-3 space-y-0">
          <div class="space-y-1">
            <CardTitle class="flex items-center gap-2">
              <Globe :size="16" class="text-brand-500" />
              {{ t('network.publicAccess.title') }}
            </CardTitle>
            <p class="text-xs text-muted-foreground">
              {{ t('network.publicAccess.subtitle') }}
            </p>
          </div>
          <span class="font-mono text-sm tabular-nums">
            {{ effectivePublicAddress() }}
          </span>
        </CardHeader>
        <CardContent class="space-y-4">
          <div>
            <Label class="text-xs uppercase tracking-wider text-muted-foreground">
              {{ t('network.publicAccess.modeLabel') }}
            </Label>
            <div class="grid sm:grid-cols-3 gap-2 mt-2">
              <button
                v-for="m in (['direct', 'playit_guided', 'playit_managed'] as const)"
                :key="m"
                type="button"
                class="rounded-lg border p-3 text-left transition-colors"
                :class="
                  localMode === m
                    ? 'border-brand-500 bg-brand-500/5'
                    : 'border-border hover:bg-accent/40'
                "
                @click="localMode = m"
              >
                <div class="text-sm font-medium">{{ t(`network.modes.${m}.label`) }}</div>
                <div class="text-xs text-muted-foreground mt-0.5 leading-snug">
                  {{ t(`network.modes.${m}.help`) }}
                </div>
              </button>
            </div>
          </div>

          <div v-if="isPlayitMode" class="space-y-1.5">
            <Label for="playit-host">{{ t('network.publicAccess.playitHostLabel') }}</Label>
            <Input
              id="playit-host"
              v-model="localPlayitHost"
              placeholder="abc-123.joinmc.link"
              class="font-mono text-xs"
            />
            <p class="text-xs text-muted-foreground">
              {{
                isPlayitManaged
                  ? t('network.publicAccess.playitHostHintManaged')
                  : t('network.publicAccess.playitHostHint')
              }}
            </p>
            <button
              v-if="
                isPlayitManaged &&
                detectedHostname &&
                detectedHostname !== localPlayitHost.trim()
              "
              type="button"
              class="text-[11px] text-brand-500 hover:underline inline-flex items-center gap-1"
              @click="useDetectedHostname"
            >
              <Check :size="11" />
              {{ t('network.publicAccess.useDetected', { host: detectedHostname }) }}
            </button>
          </div>

          <!-- Managed agent: panel runs the playit-cloud sidecar for the user -->
          <div
            v-if="isPlayitManaged"
            class="rounded-lg border border-border bg-card/40 backdrop-blur p-4 space-y-3"
          >
            <div class="flex items-center gap-2">
              <span
                class="size-2 rounded-full"
                :class="
                  agentRunning ? 'bg-emerald-500' :
                  agentBusy ? 'bg-amber-500 animate-pulse' :
                  agentQuery.data.value?.state === 'error' ? 'bg-destructive' :
                  'bg-muted-foreground/40'
                "
              />
              <span class="text-sm font-medium">
                {{ t(`network.playit.agent.state.${agentQuery.data.value?.state ?? 'absent'}`, agentQuery.data.value?.state ?? '—') }}
              </span>
              <span
                v-if="agentQuery.data.value?.error"
                class="text-xs text-destructive truncate"
                :title="agentQuery.data.value.error"
              >
                · {{ agentQuery.data.value.error }}
              </span>
              <button
                v-if="agentQuery.data.value?.state && agentQuery.data.value.state !== 'absent'"
                type="button"
                class="ml-auto inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                @click="showLogs = !showLogs"
              >
                <Terminal :size="11" />
                {{ showLogs ? t('network.playit.agent.hideLogs') : t('network.playit.agent.viewLogs') }}
              </button>
            </div>

            <!-- Static IP to paste into playit.gg's "Local IP" field.
                 Playit validates this as a literal IP (no hostnames), so
                 we expose the MC container's Docker-network address. The
                 compose file pins it to 172.30.0.10 — stable across
                 every apply / recreate / engine swap. -->
            <div
              v-if="agentQuery.data.value?.mc_container_ip"
              class="rounded-md border border-border bg-background/60 p-3 space-y-1.5"
            >
              <div class="text-[11px] uppercase tracking-wider text-muted-foreground">
                {{ t('network.playit.agent.tunnelTargetLabel') }}
              </div>
              <div class="flex items-center gap-2">
                <code class="flex-1 font-mono text-xs text-foreground">
                  {{ agentQuery.data.value.mc_container_ip }}:25565
                </code>
                <button
                  type="button"
                  class="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :title="t('common.copy')"
                  @click="copyText(`${agentQuery.data.value!.mc_container_ip}`, 'mc-ip')"
                >
                  <Check v-if="copiedKey === 'mc-ip'" :size="12" class="text-emerald-500" />
                  <Copy v-else :size="12" />
                </button>
              </div>
              <p class="text-[11px] text-muted-foreground leading-snug">
                {{ t('network.playit.agent.tunnelTargetHint') }}
              </p>
            </div>

            <!-- Secret: clear "stored" state vs explicit replacement flow.
                 An empty input with a placeholder reads as "type
                 something" — when a secret is already on file we collapse
                 to a badge so the user isn't fooled into pasting again. -->
            <div class="space-y-1.5">
              <Label for="playit-secret">{{ t('network.playit.agent.secretLabel') }}</Label>

              <!-- Saved state: badge + Replace button, no input -->
              <div
                v-if="!showSecretInput"
                class="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2"
              >
                <Check :size="14" class="text-emerald-500 shrink-0" />
                <span class="text-sm font-medium text-foreground flex-1">
                  {{ t('network.playit.agent.secretSavedBadge') }}
                </span>
                <button
                  type="button"
                  class="text-xs text-brand-500 hover:underline"
                  @click="startReplacingSecret"
                >
                  {{ t('network.playit.agent.secretReplace') }}
                </button>
              </div>

              <!-- Replace / first-time entry -->
              <div v-else class="space-y-1.5">
                <div class="flex gap-2">
                  <Input
                    id="playit-secret"
                    v-model="localSecret"
                    type="password"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="a1b2c3d4…"
                    class="font-mono text-xs flex-1"
                  />
                  <button
                    v-if="agentQuery.data.value?.has_secret"
                    type="button"
                    class="text-xs text-muted-foreground hover:text-foreground px-2"
                    @click="cancelReplacingSecret"
                  >
                    {{ t('common.cancel') }}
                  </button>
                </div>
                <p class="text-[11px] text-muted-foreground leading-snug">
                  {{ t('network.playit.agent.secretHint') }}
                </p>
              </div>
            </div>

            <div class="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                :disabled="
                  agentActions.start.isPending.value ||
                  (!agentQuery.data.value?.has_secret && !localSecret.trim())
                "
                @click="startAgent"
              >
                <Loader2
                  v-if="agentActions.start.isPending.value"
                  class="animate-spin"
                  :size="14"
                />
                <Play v-else :size="14" />
                {{
                  agentRunning
                    ? t('network.playit.agent.restart')
                    : t('network.playit.agent.start')
                }}
              </Button>
              <Button
                v-if="agentRunning || agentBusy"
                type="button"
                variant="outline"
                size="sm"
                :disabled="agentActions.stop.isPending.value"
                @click="stopAgent"
              >
                <Loader2
                  v-if="agentActions.stop.isPending.value"
                  class="animate-spin"
                  :size="14"
                />
                <Power v-else :size="14" />
                {{ t('network.playit.agent.stop') }}
              </Button>
            </div>

            <!-- Secret valid but no tunnel set up on playit.gg yet -->
            <div
              v-if="
                agentRunning &&
                agentQuery.data.value?.playit_setup === 'no_tunnel'
              "
              class="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 flex items-start gap-2.5 text-xs leading-relaxed"
            >
              <TriangleAlert :size="14" class="text-amber-500 shrink-0 mt-0.5" />
              <div class="space-y-1.5 min-w-0">
                <div class="font-medium text-foreground">
                  {{ t('network.playit.agent.noTunnelTitle') }}
                </div>
                <p class="text-muted-foreground">
                  {{ t('network.playit.agent.noTunnelBody') }}
                </p>
                <div class="flex flex-wrap items-center gap-3 pt-1">
                  <a
                    href="https://playit.gg/account/tunnels"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-1 text-brand-500 hover:underline"
                  >
                    {{ t('network.playit.agent.openDashboard') }} ↗
                  </a>
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground disabled:opacity-50"
                    :disabled="agentActions.refresh.isPending.value"
                    @click="agentActions.refresh.mutate()"
                  >
                    <RefreshCw
                      :size="11"
                      :class="agentActions.refresh.isPending.value ? 'animate-spin' : ''"
                    />
                    {{ t('network.playit.agent.refresh') }}
                  </button>
                </div>
              </div>
            </div>

            <div
              v-if="showLogs"
              class="rounded-md border border-border bg-background/60 max-h-48 overflow-auto p-2 font-mono text-[10px] leading-relaxed text-muted-foreground whitespace-pre-wrap"
            >{{ agentLogs.data.value?.logs || t('network.playit.agent.noLogs') }}</div>
          </div>

          <div v-else class="flex items-center gap-2">
            <span class="text-xs text-muted-foreground">
              {{ t('network.publicAccess.detectedAt', { ip: data.public_ip ?? '—' }) }}
            </span>
            <button
              type="button"
              class="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground"
              :title="t('network.publicAccess.refresh')"
              :disabled="refreshIp.isPending.value"
              @click="refreshIp.mutate()"
            >
              <RefreshCw :size="12" :class="refreshIp.isPending.value ? 'animate-spin' : ''" />
            </button>
          </div>
        </CardContent>
      </Card>

      <!-- ============================================================ -->
      <!-- Custom domain + DNS preview                                    -->
      <!-- ============================================================ -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('network.domain.title') }}</CardTitle>
          <p class="text-xs text-muted-foreground">{{ t('network.domain.subtitle') }}</p>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="space-y-1.5">
            <Label for="custom-domain">{{ t('network.domain.label') }}</Label>
            <Input
              id="custom-domain"
              v-model="localDomain"
              placeholder="mc.example.com"
              class="font-mono text-xs max-w-md"
              autocomplete="off"
              spellcheck="false"
            />
            <p class="text-xs text-muted-foreground">{{ t('network.domain.hint') }}</p>
          </div>

          <div v-if="sortedDnsRecords.length" class="space-y-1">
            <div class="flex items-center justify-between">
              <Label class="text-xs uppercase tracking-wider text-muted-foreground">
                {{ t('network.domain.recordsToAdd') }}
              </Label>
              <span class="text-[11px] text-muted-foreground italic">
                {{ t('network.domain.recordsHint') }}
              </span>
            </div>
            <div class="rounded-lg border border-border overflow-hidden">
              <table class="w-full text-xs">
                <thead class="bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                  <tr>
                    <th class="px-3 py-2 text-left font-medium w-16">Type</th>
                    <th class="px-3 py-2 text-left font-medium">Name</th>
                    <th class="px-3 py-2 text-left font-medium">Value</th>
                    <th class="px-3 py-2 text-right font-medium w-14">TTL</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(rec, i) in sortedDnsRecords"
                    :key="i"
                    class="border-t border-border align-top"
                  >
                    <td class="px-3 py-2">
                      <span
                        class="inline-flex items-center rounded-full bg-muted text-foreground px-2 py-0.5 font-mono"
                      >
                        {{ rec.type }}
                      </span>
                    </td>
                    <td class="px-3 py-2 font-mono">
                      <button
                        type="button"
                        class="group inline-flex items-center gap-1.5 hover:text-foreground"
                        @click="copyText(rec.name, `name-${i}`)"
                      >
                        <span class="truncate">{{ rec.name }}</span>
                        <Check v-if="copiedKey === `name-${i}`" :size="10" class="text-brand-500" />
                        <Copy v-else :size="10" class="opacity-40 group-hover:opacity-100" />
                      </button>
                    </td>
                    <td class="px-3 py-2 font-mono">
                      <button
                        type="button"
                        class="group inline-flex items-center gap-1.5 hover:text-foreground max-w-full"
                        @click="copyText(rec.value, `value-${i}`)"
                      >
                        <span class="truncate">{{ rec.value }}</span>
                        <Check v-if="copiedKey === `value-${i}`" :size="10" class="text-brand-500 shrink-0" />
                        <Copy v-else :size="10" class="opacity-40 group-hover:opacity-100 shrink-0" />
                      </button>
                      <div
                        v-if="rec.comment"
                        class="text-[10px] text-muted-foreground mt-0.5 italic font-sans leading-snug"
                      >
                        {{ rec.comment }}
                      </div>
                    </td>
                    <td class="px-3 py-2 text-right text-muted-foreground tabular-nums">
                      {{ rec.ttl }}s
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div
            v-else-if="localDomain && !sortedDnsRecords.length"
            class="rounded-lg border border-amber-400/30 bg-amber-400/5 p-3 text-xs text-amber-300 flex items-start gap-2"
          >
            <TriangleAlert :size="14" class="shrink-0 mt-0.5" />
            <span>{{ t('network.domain.cantPreview') }}</span>
          </div>
        </CardContent>
      </Card>

      <!-- Save bar (sticky) for profile changes -->
      <Transition name="view-fade">
        <div
          v-if="profileDirty"
          class="fixed bottom-4 inset-x-4 sm:left-auto sm:right-6 sm:bottom-6 z-30 flex items-center gap-3 rounded-xl border border-border bg-card/90 backdrop-blur-md shadow-2xl px-4 py-3 max-w-fit"
        >
          <span class="size-1.5 rounded-full bg-amber-400 animate-pulse" />
          <span class="text-sm">{{ t('settings.unsaved') }}</span>
          <Button :disabled="updateProfile.isPending.value" @click="saveProfile">
            <Loader2 v-if="updateProfile.isPending.value" class="animate-spin" />
            {{ t('common.save') }}
          </Button>
        </div>
      </Transition>

      <!-- ============================================================ -->
      <!-- Allocations                                                    -->
      <!-- ============================================================ -->
      <Card>
        <CardHeader class="flex flex-row items-center justify-between gap-3 space-y-0">
          <div class="space-y-1">
            <CardTitle>{{ t('network.allocations.title') }}</CardTitle>
            <p class="text-xs text-muted-foreground">
              {{ t('network.allocations.subtitle') }}
            </p>
          </div>
          <Button size="sm" @click="allocFormOpen = !allocFormOpen">
            <Plus />
            {{ t('network.allocations.add') }}
          </Button>
        </CardHeader>
        <CardContent class="space-y-4">
          <Transition name="view-fade">
            <div
              v-if="allocFormOpen"
              class="rounded-lg border border-border p-4 space-y-3"
            >
              <div>
                <Label class="text-xs">{{ t('network.allocations.preset') }}</Label>
                <div class="flex flex-wrap gap-1 pt-1">
                  <button
                    v-for="p in ALLOC_PRESETS"
                    :key="p.label"
                    type="button"
                    class="text-[11px] rounded-md border border-border px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                    @click="applyPreset(p)"
                  >
                    {{ p.label }} :{{ p.container_port }}/{{ p.protocol }}
                  </button>
                </div>
              </div>

              <div class="grid sm:grid-cols-4 gap-3">
                <div class="sm:col-span-2 space-y-1">
                  <Label for="alloc-label">{{ t('common.name') }}</Label>
                  <Input
                    id="alloc-label"
                    v-model="allocLabel"
                    :placeholder="t('network.allocations.labelPlaceholder')"
                  />
                </div>
                <div class="space-y-1">
                  <Label for="alloc-host-port">{{ t('network.allocations.hostPort') }}</Label>
                  <Input
                    id="alloc-host-port"
                    v-model.number="allocHostPort"
                    type="number"
                    min="1"
                    max="65535"
                    placeholder="8100"
                  />
                </div>
                <div class="space-y-1">
                  <Label for="alloc-container-port">{{ t('network.allocations.containerPort') }}</Label>
                  <Input
                    id="alloc-container-port"
                    v-model.number="allocContainerPort"
                    type="number"
                    min="1"
                    max="65535"
                    placeholder="8100"
                  />
                </div>
              </div>

              <div class="flex items-center gap-3 text-sm">
                <Label>{{ t('network.allocations.protocol') }}</Label>
                <div class="inline-flex rounded-md border border-border bg-card p-0.5 gap-0.5">
                  <button
                    v-for="p in (['tcp', 'udp'] as const)"
                    :key="p"
                    type="button"
                    class="px-3 py-0.5 text-xs font-mono rounded text-muted-foreground transition-colors"
                    :class="allocProto === p ? 'bg-accent text-foreground' : 'hover:text-foreground'"
                    @click="allocProto = p"
                  >
                    {{ p.toUpperCase() }}
                  </button>
                </div>
              </div>

              <div class="flex justify-end gap-2 pt-1">
                <Button variant="ghost" size="sm" @click="allocFormOpen = false; resetAllocForm()">
                  {{ t('common.cancel') }}
                </Button>
                <Button
                  size="sm"
                  :disabled="
                    !allocLabel.trim()
                      || !allocHostPort
                      || !allocContainerPort
                      || allocations.create.isPending.value
                  "
                  @click="onSubmitAllocation"
                >
                  <Loader2 v-if="allocations.create.isPending.value" class="animate-spin" />
                  <Plus v-else />
                  {{ t('network.allocations.add') }}
                </Button>
              </div>
            </div>
          </Transition>

          <div class="rounded-lg border border-border overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th class="px-3 py-2 text-left font-medium">{{ t('common.name') }}</th>
                  <th class="px-3 py-2 text-left font-medium font-mono">
                    {{ t('network.allocations.hostPort') }}
                  </th>
                  <th class="px-3 py-2 text-left font-medium font-mono">
                    {{ t('network.allocations.containerPort') }}
                  </th>
                  <th class="px-3 py-2 text-left font-medium">
                    {{ t('network.allocations.protocol') }}
                  </th>
                  <th class="w-16 px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                <tr v-if="!data.allocations.length">
                  <td colspan="5" class="px-4 py-8 text-center text-xs text-muted-foreground">
                    {{ t('network.allocations.empty') }}
                  </td>
                </tr>
                <tr
                  v-for="alloc in data.allocations"
                  :key="alloc.id"
                  class="border-t border-border hover:bg-accent/30 transition-colors"
                >
                  <td class="px-3 py-2 font-medium">{{ alloc.label }}</td>
                  <td class="px-3 py-2 font-mono tabular-nums">{{ alloc.host_port }}</td>
                  <td class="px-3 py-2 font-mono tabular-nums">{{ alloc.container_port }}</td>
                  <td class="px-3 py-2">
                    <span class="text-xs font-mono text-muted-foreground">{{ alloc.protocol }}</span>
                  </td>
                  <td class="px-3 py-2 text-right">
                    <button
                      type="button"
                      class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      :aria-label="t('common.delete')"
                      @click="onDeleteAllocation(alloc)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
