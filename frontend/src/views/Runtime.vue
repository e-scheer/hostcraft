<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Activity, Cpu, Loader2, RotateCcw, Save, TriangleAlert } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  createSafetyBackup,
  useApplyRuntime,
  useRuntime,
  useRuntimeOptions,
} from '@/composables/useRuntime'
import { useDialogStore } from '@/stores/dialog'
import { useUpdateWatchdog, useWatchdog } from '@/composables/useWatchdog'
import type { RuntimeSnapshot } from '@/lib/api'

const { t } = useI18n()
const dialog = useDialogStore()
const runtimeQuery = useRuntime()
const optionsQuery = useRuntimeOptions()
const apply = useApplyRuntime()
const watchdog = useWatchdog()
const updateWatchdog = useUpdateWatchdog()

function onWatchdogToggle(enabled: boolean) {
  updateWatchdog.mutate({ enabled })
}
function onWatchdogThreshold(seconds: number) {
  updateWatchdog.mutate({ threshold_seconds: seconds })
}
function onWatchdogMaxRestarts(n: number) {
  updateWatchdog.mutate({ max_restarts_per_hour: n })
}

interface Local {
  TYPE: string
  VERSION: string
  MEMORY: string
  USE_AIKAR_FLAGS: boolean
  JVM_OPTS: string
  JVM_XX_OPTS: string
}

function fromSnapshot(data: RuntimeSnapshot): Local {
  const v = data.values
  return {
    TYPE: v.TYPE || 'VANILLA',
    VERSION: v.VERSION || 'LATEST',
    MEMORY: v.MEMORY || '4G',
    USE_AIKAR_FLAGS: (v.USE_AIKAR_FLAGS || '').toLowerCase() === 'true',
    JVM_OPTS: v.JVM_OPTS || '',
    JVM_XX_OPTS: v.JVM_XX_OPTS || '',
  }
}

const local = ref<Local>({
  TYPE: 'VANILLA',
  VERSION: 'LATEST',
  MEMORY: '4G',
  USE_AIKAR_FLAGS: true,
  JVM_OPTS: '',
  JVM_XX_OPTS: '',
})
const initial = ref<Local>({ ...local.value })

// Java/image tag — tracked alongside env values, but sent as a separate
// `image_tag` field to the runtime endpoint (it triggers an image swap,
// not just an env update).
const localImageTag = ref<string>('latest')
const initialImageTag = ref<string>('latest')

const isDirty = computed(() => {
  const a = local.value
  const b = initial.value
  return (
    a.TYPE !== b.TYPE ||
    a.VERSION !== b.VERSION ||
    a.MEMORY !== b.MEMORY ||
    a.USE_AIKAR_FLAGS !== b.USE_AIKAR_FLAGS ||
    a.JVM_OPTS !== b.JVM_OPTS ||
    a.JVM_XX_OPTS !== b.JVM_XX_OPTS ||
    localImageTag.value !== initialImageTag.value
  )
})

// Watches read isDirty — must be declared AFTER it. With `immediate: true`
// the callbacks run synchronously during setup, so a TDZ on isDirty here
// would crash the component before any render happens.
watch(
  () => runtimeQuery.data.value?.image_tag,
  (tag) => {
    if (tag && !isDirty.value) {
      localImageTag.value = tag
      initialImageTag.value = tag
    }
  },
  { immediate: true },
)

watch(
  () => runtimeQuery.data.value,
  (data) => {
    if (!data) return
    if (!isDirty.value) {
      const parsed = fromSnapshot(data)
      local.value = parsed
      initial.value = { ...parsed }
    }
  },
  { immediate: true },
)

const javaCompat = computed(() => {
  const opt = optionsQuery.data.value
  if (!opt) return null
  const minRequired = opt.min_java_for_current_mc
  const recommended = opt.recommended_java_for_current_mc
  const selected = opt.java_tags.find((j) => j.tag === localImageTag.value)
  if (!selected) return null
  // ``latest`` (java=0) lets itzg pick — always considered fine.
  if (selected.java === 0 || !minRequired) {
    return {
      level: 'ok' as const,
      java: selected.java,
      min: minRequired ?? 0,
      recommended: recommended ?? 0,
    }
  }
  if (selected.java < minRequired) {
    // Too old to run at all — hard error.
    return {
      level: 'error' as const,
      java: selected.java,
      min: minRequired,
      recommended: recommended ?? 0,
    }
  }
  if (recommended && selected.java > recommended) {
    // Above the typical target for this MC: still runs, but native
    // libraries bundled with old mods (e.g. spark's async-profiler)
    // may crash. Surface this as a soft warning, not a block.
    return {
      level: 'warn' as const,
      java: selected.java,
      min: minRequired,
      recommended,
    }
  }
  return {
    level: 'ok' as const,
    java: selected.java,
    min: minRequired,
    recommended: recommended ?? 0,
  }
})

const riskyKeys = computed(() => runtimeQuery.data.value?.risky_keys ?? ['TYPE', 'VERSION'])
const isRiskyChange = computed(() => {
  return riskyKeys.value.some(
    (k) => local.value[k as keyof Local] !== initial.value[k as keyof Local],
  )
})

// Engine families — same family means existing mods/plugins/world keep
// working (Paper → Spigot is fine). Different family triggers a full
// data-dir reset on apply (we keep only admin/identity files).
const ENGINE_FAMILY: Record<string, string> = {
  PAPER: 'bukkit', PURPUR: 'bukkit', FOLIA: 'bukkit',
  SPIGOT: 'bukkit', BUKKIT: 'bukkit',
  FORGE: 'forge', NEOFORGE: 'neoforge',
  FABRIC: 'fabric', QUILT: 'fabric',
  VANILLA: 'vanilla',
}

const familyChange = computed(() => {
  const oldT = (initial.value.TYPE || '').toUpperCase()
  const newT = (local.value.TYPE || '').toUpperCase()
  if (!oldT || !newT) return null
  const oldFam = ENGINE_FAMILY[oldT]
  const newFam = ENGINE_FAMILY[newT]
  if (!oldFam || !newFam || oldFam === newFam) return null
  return { oldType: oldT, newType: newT }
})

function applyValues(opts: { engineReset?: boolean } = {}) {
  const tagChanged = localImageTag.value !== initialImageTag.value
  apply.mutate(
    {
      values: local.value as unknown as Record<string, string | boolean>,
      image_tag: tagChanged ? localImageTag.value : undefined,
      engine_reset: opts.engineReset,
    },
    {
      onSuccess: (data) => {
        const parsed = fromSnapshot(data)
        local.value = parsed
        initial.value = { ...parsed }
        localImageTag.value = data.image_tag
        initialImageTag.value = data.image_tag
      },
    },
  )
}

/** Mark the form as committed so the route guard stops blocking navigation
 * while the safety backup + apply run in the background. The user has
 * already expressed intent — there's nothing left to "save". */
function commitDirty() {
  initial.value = { ...local.value }
  initialImageTag.value = localImageTag.value
}

async function onApply() {
  if (!isDirty.value || apply.isPending.value) return

  // Engine-family swap: world data, configs, loader payloads — all of it
  // is engine-specific and likely to crash the new server. Step 1 — full
  // reset (recommended, recoverable from the safety backup) vs keep at
  // own risk (almost always crash-loops).
  let engineReset = false
  const fam = familyChange.value
  if (fam) {
    const wipeChoice = await dialog.ask({
      title: t('runtime.engineSwap.title', {
        old: fam.oldType.toLowerCase(),
        new: fam.newType.toLowerCase(),
      }),
      description: t('runtime.engineSwap.description', {
        new: fam.newType.toLowerCase(),
      }),
      cancelLabel: t('common.cancel'),
      alternativeLabel: t('runtime.engineSwap.keep'),
      alternativeVariant: 'outline',
      confirmLabel: t('runtime.engineSwap.wipe'),
      variant: 'destructive',
    })
    if (wipeChoice === 'cancel') return
    if (wipeChoice === 'confirm') engineReset = true
    // 'alternative' → keep everything, engineReset stays false
  }

  // Risky change: TYPE or VERSION moved → three-way prompt:
  //   - Cancel
  //   - Apply without backup (alternative)
  //   - Backup, then apply (default confirm)
  if (isRiskyChange.value) {
    const choice = await dialog.ask({
      title: t('runtime.risky.title'),
      description: t('runtime.risky.description'),
      cancelLabel: t('common.cancel'),
      alternativeLabel: t('runtime.risky.skipBackup'),
      alternativeVariant: 'outline',
      confirmLabel: t('runtime.risky.withBackup'),
      variant: 'destructive',
    })
    if (choice === 'cancel') return

    // User committed — clear the dirty flag immediately so they can browse
    // away while the (possibly long) backup + apply runs.
    commitDirty()

    if (choice === 'alternative') {
      applyValues({ engineReset })
      return
    }

    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const toastId = toast.loading(t('runtime.risky.backupRunning'))
    try {
      await createSafetyBackup(`safety-${stamp}`)
      toast.success(t('runtime.risky.backupReady'), { id: toastId, duration: 3000 })
    } catch (err) {
      toast.error(t('runtime.risky.backupFailed'), {
        id: toastId,
        description: err instanceof Error ? err.message : String(err),
      })
      return
    }
    applyValues({ engineReset })
    return
  }

  // Non-risky change: simple confirm + apply.
  const ok = await dialog.confirm({
    title: t('runtime.warningTitle'),
    description: t('runtime.warningDescription'),
    confirmLabel: t('runtime.apply'),
    variant: 'destructive',
  })
  if (!ok) return
  commitDirty()
  applyValues()
}

function onReset() {
  local.value = { ...initial.value }
}

async function onCleanInstall() {
  if (apply.isPending.value) return
  const ok = await dialog.confirm({
    title: t('runtime.cleanInstall.title'),
    description: t('runtime.cleanInstall.description'),
    confirmLabel: t('runtime.cleanInstall.confirm'),
    cancelLabel: t('common.cancel'),
    variant: 'destructive',
  })
  if (!ok) return
  // No env or image change — engine_reset alone forces a recreate, the
  // backend wipes the data dir, and the new container bootstraps fresh.
  apply.mutate({
    values: {},
    engine_reset: true,
  })
}

onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  const ok = await dialog.confirm({
    title: t('common.unsavedTitle'),
    description: t('settings.discardConfirm'),
    confirmLabel: t('common.discard'),
    variant: 'destructive',
  })
  return ok
})
</script>

<template>
  <div class="space-y-6 pb-24">
    <header class="space-y-1">
      <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <Cpu :size="22" class="text-brand-500" />
        {{ t('runtime.title') }}
      </h2>
      <p class="text-sm text-muted-foreground">{{ t('runtime.subtitle') }}</p>
    </header>

    <div
      class="rounded-lg border border-amber-400/30 bg-amber-400/5 p-3 text-xs text-amber-300 flex items-start gap-2"
    >
      <TriangleAlert :size="14" class="shrink-0 mt-0.5" />
      <div>
        <div class="font-medium">{{ t('runtime.warningTitle') }}</div>
        <div class="text-amber-300/80 leading-relaxed mt-0.5">
          {{ t('runtime.warningDescription') }}
        </div>
      </div>
    </div>

    <div
      v-if="runtimeQuery.isPending.value && !runtimeQuery.data.value"
      class="flex items-center gap-2 text-muted-foreground text-sm"
    >
      <Loader2 class="animate-spin" :size="14" />
      {{ t('runtime.loading') }}
    </div>

    <div
      v-else-if="runtimeQuery.isError.value"
      class="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
    >
      {{ runtimeQuery.error.value?.message ?? t('runtime.loadFailed') }}
    </div>

    <template v-else>
      <!-- Server stack -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('runtime.sections.stack') }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-5">
          <!-- TYPE -->
          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-type" class="block">{{ t('runtime.fields.TYPE.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">TYPE</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.TYPE.help') }}
              </p>
            </div>
            <select
              id="rt-type"
              v-model="local.TYPE"
              class="h-9 max-w-[16rem] rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
            >
              <option
                v-for="opt in optionsQuery.data.value?.types ?? []"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </option>
              <option
                v-if="local.TYPE && !optionsQuery.data.value?.types.some((o) => o.value === local.TYPE)"
                :value="local.TYPE"
              >
                {{ local.TYPE }} (custom)
              </option>
            </select>
          </div>

          <!-- VERSION -->
          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-version" class="block">{{ t('runtime.fields.VERSION.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">VERSION</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.VERSION.help') }}
              </p>
            </div>
            <div class="space-y-1.5 max-w-[16rem]">
              <Input id="rt-version" v-model="local.VERSION" placeholder="LATEST" />
              <div class="flex flex-wrap gap-1">
                <button
                  v-for="preset in optionsQuery.data.value?.version_presets ?? []"
                  :key="preset"
                  type="button"
                  class="text-[11px] font-mono rounded-md px-2 py-0.5 border border-border text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :class="
                    local.VERSION === preset ? 'border-brand-500/60 bg-brand-500/10 text-brand-300' : ''
                  "
                  @click="local.VERSION = preset"
                >
                  {{ preset }}
                </button>
              </div>
            </div>
          </div>

          <!-- Java image tag -->
          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-java" class="block">{{ t('runtime.fields.JAVA.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">image tag</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.JAVA.help') }}
              </p>
            </div>
            <div class="space-y-1.5 max-w-[16rem]">
              <select
                id="rt-java"
                v-model="localImageTag"
                class="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option
                  v-for="j in optionsQuery.data.value?.java_tags ?? []"
                  :key="j.tag"
                  :value="j.tag"
                  :disabled="
                    j.java > 0 &&
                    optionsQuery.data.value?.min_java_for_current_mc != null &&
                    j.java < optionsQuery.data.value.min_java_for_current_mc
                  "
                >
                  {{ j.label }}{{
                    j.java > 0 &&
                    optionsQuery.data.value?.recommended_java_for_current_mc === j.java
                      ? '  ★ ' + t('runtime.fields.JAVA.recommendedBadge')
                      : ''
                  }}
                </option>
              </select>

              <!-- Too old: hard error. -->
              <p
                v-if="javaCompat?.level === 'error'"
                class="inline-flex items-center gap-1.5 text-[11px] text-destructive"
              >
                <TriangleAlert :size="11" />
                {{
                  t('runtime.fields.JAVA.tooOld', {
                    min: javaCompat.min,
                    mc: optionsQuery.data.value?.resolved_mc_version ?? '',
                  })
                }}
              </p>

              <!-- Above the recommended target: native libs in older
                   mods may crash (e.g. spark's async-profiler on Java
                   25+). Allow but warn. -->
              <p
                v-else-if="javaCompat?.level === 'warn'"
                class="inline-flex items-start gap-1.5 text-[11px] text-amber-500 leading-snug"
              >
                <TriangleAlert :size="11" class="mt-0.5 shrink-0" />
                <span>
                  {{
                    t('runtime.fields.JAVA.tooNew', {
                      recommended: javaCompat.recommended,
                      mc: optionsQuery.data.value?.resolved_mc_version ?? '',
                    })
                  }}
                </span>
              </p>

              <!-- Healthy: just show what the minimum is. -->
              <p
                v-else-if="
                  javaCompat &&
                  javaCompat.java > 0 &&
                  optionsQuery.data.value?.min_java_for_current_mc
                "
                class="text-[11px] text-muted-foreground"
              >
                {{
                  t('runtime.fields.JAVA.minHint', {
                    min: optionsQuery.data.value.min_java_for_current_mc,
                    mc: optionsQuery.data.value.resolved_mc_version ?? '',
                  })
                }}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Memory & JVM -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('runtime.sections.memory') }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-5">
          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-mem" class="block">{{ t('runtime.fields.MEMORY.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">MEMORY</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.MEMORY.help') }}
              </p>
            </div>
            <Input id="rt-mem" v-model="local.MEMORY" class="max-w-[12rem]" placeholder="4G" />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-aikar" class="block">{{ t('runtime.fields.USE_AIKAR_FLAGS.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">USE_AIKAR_FLAGS</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.USE_AIKAR_FLAGS.help') }}
              </p>
            </div>
            <div class="flex items-center">
              <Switch id="rt-aikar" v-model="local.USE_AIKAR_FLAGS" />
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-opts" class="block">{{ t('runtime.fields.JVM_OPTS.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">JVM_OPTS</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.JVM_OPTS.help') }}
              </p>
            </div>
            <Input id="rt-opts" v-model="local.JVM_OPTS" placeholder="-Dfile.encoding=UTF-8" />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6">
            <div>
              <Label for="rt-xx" class="block">{{ t('runtime.fields.JVM_XX_OPTS.label') }}</Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5">JVM_XX_OPTS</p>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('runtime.fields.JVM_XX_OPTS.help') }}
              </p>
            </div>
            <Input id="rt-xx" v-model="local.JVM_XX_OPTS" placeholder="-XX:+UseG1GC" />
          </div>
        </CardContent>
      </Card>


      <!-- ================================================================ -->
      <!-- Resilience / Watchdog                                              -->
      <!-- ================================================================ -->
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Activity :size="16" class="text-brand-500" />
            {{ t('watchdog.title') }}
          </CardTitle>
          <p class="text-xs text-muted-foreground mt-1">{{ t('watchdog.subtitle') }}</p>
        </CardHeader>
        <CardContent class="space-y-5">
          <div
            class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6 sm:items-center"
          >
            <div>
              <Label class="block">{{ t('watchdog.enabledLabel') }}</Label>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('watchdog.enabledHelp') }}
              </p>
            </div>
            <div class="flex items-center gap-3">
              <Switch
                :model-value="watchdog.data.value?.enabled ?? false"
                @update:model-value="onWatchdogToggle"
              />
              <span
                v-if="watchdog.data.value?.total_restarts"
                class="text-xs text-muted-foreground"
              >
                {{ t('watchdog.totalRestarts', { n: watchdog.data.value.total_restarts }) }}
              </span>
            </div>
          </div>

          <div
            v-if="watchdog.data.value?.enabled"
            class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6 sm:items-center"
          >
            <div>
              <Label for="wd-threshold" class="block">{{ t('watchdog.thresholdLabel') }}</Label>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('watchdog.thresholdHelp') }}
              </p>
            </div>
            <Input
              id="wd-threshold"
              type="number"
              min="30"
              max="3600"
              step="30"
              class="max-w-[10rem]"
              :model-value="watchdog.data.value?.threshold_seconds ?? 120"
              @change="onWatchdogThreshold(Number(($event.target as HTMLInputElement).value))"
            />
          </div>

          <div
            v-if="watchdog.data.value?.enabled"
            class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6 sm:items-center"
          >
            <div>
              <Label for="wd-max" class="block">{{ t('watchdog.maxLabel') }}</Label>
              <p class="text-xs text-muted-foreground mt-1 leading-snug">
                {{ t('watchdog.maxHelp') }}
              </p>
            </div>
            <Input
              id="wd-max"
              type="number"
              min="1"
              max="20"
              class="max-w-[10rem]"
              :model-value="watchdog.data.value?.max_restarts_per_hour ?? 3"
              @change="onWatchdogMaxRestarts(Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </CardContent>
      </Card>

      <!-- Danger zone — clean install -->
      <Card class="border-destructive/30">
        <CardHeader>
          <CardTitle class="flex items-center gap-2 text-destructive">
            <TriangleAlert :size="18" />
            {{ t('runtime.cleanInstall.title') }}
          </CardTitle>
          <p class="text-xs text-muted-foreground mt-1 leading-relaxed">
            {{ t('runtime.cleanInstall.subtitle') }}
          </p>
        </CardHeader>
        <CardContent class="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="destructive"
            size="sm"
            :disabled="apply.isPending.value"
            @click="onCleanInstall"
          >
            <Loader2 v-if="apply.isPending.value" class="animate-spin" />
            <TriangleAlert v-else :size="14" />
            {{ t('runtime.cleanInstall.confirm') }}
          </Button>
          <span class="text-[11px] text-muted-foreground italic">
            {{ t('runtime.cleanInstall.hint') }}
          </span>
        </CardContent>
      </Card>
    </template>

    <Transition name="view-fade">
      <div
        v-if="isDirty"
        class="fixed bottom-4 inset-x-4 sm:left-auto sm:right-6 sm:bottom-6 z-30 flex items-center gap-3 rounded-xl border border-border bg-card/90 backdrop-blur-md shadow-2xl px-4 py-3 max-w-fit"
      >
        <span class="inline-flex items-center gap-1.5 text-sm">
          <span class="size-1.5 rounded-full bg-amber-400 animate-pulse" />
          {{ t('settings.unsaved') }}
        </span>
        <span
          v-if="isRiskyChange"
          class="inline-flex items-center gap-1.5 text-[11px] rounded-full border border-amber-400/40 bg-amber-400/10 text-amber-300 px-2 py-0.5"
        >
          {{ t('runtime.risky.title') }}
        </span>
        <Button variant="ghost" size="sm" :disabled="apply.isPending.value" @click="onReset">
          <RotateCcw />
          {{ t('common.cancel') }}
        </Button>
        <Button :disabled="apply.isPending.value" @click="onApply">
          <Loader2 v-if="apply.isPending.value" class="animate-spin" />
          <Save v-else />
          {{ apply.isPending.value ? t('runtime.applying') : t('runtime.apply') }}
        </Button>
      </div>
    </Transition>
  </div>
</template>
