<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  Box,
  Boxes,
  Check,
  Download,
  ExternalLink,
  FileQuestion,
  Info,
  Loader2,
  Package,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  Users,
  X,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import EmptyState from '@/components/EmptyState.vue'
import ProjectIcon from '@/components/ProjectIcon.vue'
import {
  useInspectUpload,
  useInstallMod,
  useInstalledMods,
  useModSearch,
  useModTarget,
  useUninstallMod,
  useUploadInstall,
} from '@/composables/useMods'
import { useDialogStore } from '@/stores/dialog'
import type {
  ManualInspectPayload,
  ManualMeta,
  ModProvider,
  ModSearchHit,
  InstalledMod,
} from '@/lib/api'

const { t } = useI18n()
const dialog = useDialogStore()

type Tab = 'search' | 'installed' | 'upload'
const tab = ref<Tab>('search')

const target = useModTarget()
const installed = useInstalledMods()

// Debounced search input
const searchInput = ref('')
const debounced = ref('')
let debounceHandle: number | null = null
watch(searchInput, (q) => {
  if (debounceHandle != null) window.clearTimeout(debounceHandle)
  debounceHandle = window.setTimeout(() => {
    debounced.value = q
  }, 300)
})

// Search shows everything by default; install enforces compatibility.
// The toggle lets the user opt into a strict pre-filter when they prefer
// a shorter, vetted list.
const strictVersion = ref(false)
const search = useModSearch(debounced, strictVersion)
const install = useInstallMod()
const uninstall = useUninstallMod()

const isUnsupported = computed(() => target.data.value?.kind === 'none')

const installedIndex = computed(() => {
  const map = new Map<string, InstalledMod>()
  for (const m of installed.data.value?.tracked ?? []) {
    map.set(`${m.provider}:${m.project_id}`, m)
  }
  return map
})

function isInstalled(hit: ModSearchHit): boolean {
  return installedIndex.value.has(`${hit.provider}:${hit.project_id}`)
}

function isModpack(hit: ModSearchHit): boolean {
  return hit.project_type === 'modpack'
}

function compatStatus(hit: ModSearchHit): 'ok' | 'mismatch' | 'unknown' {
  // Use the truthful per-loader signal computed by the backend.
  if (hit.installable_for_target === true) return 'ok'
  if (hit.installable_for_target === false) {
    // We know it's not installable — show the precise range when we have
    // one (the loader has *some* releases, just not for this MC version).
    return hit.compat_mc_versions_for_loader.length > 0 ? 'mismatch' : 'unknown'
  }
  return 'unknown'
}

function versionRange(versions: string[]): { min: string; max: string } | null {
  const releases = versions.filter((v) => /^\d+\.\d+(\.\d+){0,2}$/.test(v))
  if (releases.length === 0) return null
  const sorted = [...releases].sort((a, b) => {
    const pa = a.split('.').map(Number)
    const pb = b.split('.').map(Number)
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
      const d = (pa[i] ?? 0) - (pb[i] ?? 0)
      if (d !== 0) return d
    }
    return 0
  })
  return { min: sorted[0], max: sorted[sorted.length - 1] }
}

function compatTooltip(hit: ModSearchHit): string {
  // Prefer the per-loader range when available — it reflects what's
  // actually installable on this server.
  const list = hit.compat_mc_versions_for_loader.length > 0
    ? hit.compat_mc_versions_for_loader
    : hit.mc_versions
  const range = versionRange(list)
  const mc = target.data.value?.mc_version ?? ''
  if (!range) return t('mods.compat.unknownTooltip')
  const supported =
    range.min === range.max
      ? t('mods.compat.requiresExact', { v: range.min })
      : t('mods.compat.requiresRange', { min: range.min, max: range.max })
  return mc ? `${supported} · ${t('mods.compat.youHave', { v: mc })}` : supported
}

function mismatchLabel(hit: ModSearchHit): string {
  const list = hit.compat_mc_versions_for_loader.length > 0
    ? hit.compat_mc_versions_for_loader
    : hit.mc_versions
  const range = versionRange(list)
  if (!range) return t('mods.compat.mismatch')
  return range.min === range.max ? range.min : `${range.min} – ${range.max}`
}

function fmtDownloads(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const installingId = ref<string | null>(null)
async function onInstall(hit: ModSearchHit) {
  installingId.value = `${hit.provider}:${hit.project_id}`
  try {
    await install.mutateAsync({ provider: hit.provider as ModProvider, project_id: hit.project_id })
  } finally {
    installingId.value = null
  }
}

async function onUninstall(m: InstalledMod) {
  const ok = await dialog.confirm({
    title: t('mods.confirmUninstallTitle', { name: m.title }),
    description: t('mods.confirmUninstallDesc'),
    confirmLabel: t('mods.uninstall'),
    variant: 'destructive',
  })
  if (ok) uninstall.mutate(m.id)
}

const providerLabel: Record<ModProvider, string> = {
  modrinth: 'Modrinth',
  hangar: 'Hangar',
}

// --- Manual upload ----------------------------------------------------------
const inspectUpload = useInspectUpload()
const uploadInstall = useUploadInstall()

const uploadFile = ref<File | null>(null)
const uploadInspect = ref<ManualInspectPayload | null>(null)
const uploadInputRef = ref<HTMLInputElement | null>(null)
// When we couldn't tell mod-vs-plugin from the archive, the UI asks the
// user to pick. This holds their override.
const forceKind = ref<'mod' | 'plugin' | ''>('')

function pickUploadFile() { uploadInputRef.value?.click() }
function resetUpload() {
  uploadFile.value = null
  uploadInspect.value = null
  forceKind.value = ''
  if (uploadInputRef.value) uploadInputRef.value.value = ''
}

async function onUploadFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploadFile.value = file
  forceKind.value = ''
  uploadInspect.value = null
  uploadInspect.value = await inspectUpload.mutateAsync(file).catch(() => null)
}

function commitUpload() {
  const file = uploadFile.value
  if (!file) return
  const meta = uploadInspect.value?.meta
  const kindOverride =
    meta && meta.kind !== 'mod' && meta.kind !== 'plugin' && forceKind.value
      ? forceKind.value
      : undefined
  uploadInstall.mutate({ file, force_kind: kindOverride }, {
    onSuccess: () => resetUpload(),
  })
}

const verdictColor = (v: 'ok' | 'mismatch' | 'unknown' | undefined) =>
  v === 'ok'
    ? 'text-emerald-500'
    : v === 'mismatch'
      ? 'text-amber-500'
      : 'text-muted-foreground'

// Curated upstream sources for the user to grab a .jar from when the
// in-panel marketplace doesn't have what they need.
const sources = [
  { id: 'modrinth', label: 'Modrinth', host: 'modrinth.com', url: 'https://modrinth.com/mods', tag: 'mods + plugins + modpacks' },
  { id: 'hangar', label: 'Hangar', host: 'hangar.papermc.io', url: 'https://hangar.papermc.io', tag: 'paper plugins' },
  { id: 'curseforge', label: 'CurseForge', host: 'curseforge.com', url: 'https://www.curseforge.com/minecraft/mc-mods', tag: 'forge / neoforge / fabric' },
  { id: 'spigot', label: 'SpigotMC', host: 'spigotmc.org', url: 'https://www.spigotmc.org/resources/', tag: 'spigot / paper plugins' },
] as const
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div class="space-y-1">
        <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Package :size="22" class="text-brand-500" />
          {{ t('mods.title') }}
        </h2>
        <p class="text-sm text-muted-foreground">{{ t('mods.subtitle') }}</p>
      </div>

      <!-- Target indicator -->
      <div
        v-if="target.data.value"
        class="inline-flex items-center gap-2 rounded-lg border border-border bg-card/40 backdrop-blur px-3 py-1.5 text-xs"
        :title="
          target.data.value.mc_version_alias
            ? t('mods.versionResolved', {
                alias: target.data.value.mc_version_alias,
                resolved: target.data.value.mc_version,
              })
            : ''
        "
      >
        <Box :size="14" class="text-brand-500" />
        <span class="font-medium">{{ target.data.value.loader_label }}</span>
        <span class="text-muted-foreground" v-if="target.data.value.mc_version">
          ·
          <span class="font-mono">{{ target.data.value.mc_version }}</span>
          <span
            v-if="target.data.value.mc_version_alias"
            class="text-muted-foreground/70 ml-1"
          >
            ({{ target.data.value.mc_version_alias }})
          </span>
        </span>
        <span
          class="ml-1 px-1.5 py-0.5 rounded text-[10px] font-mono uppercase"
          :class="
            target.data.value.kind === 'none'
              ? 'bg-amber-500/10 text-amber-500'
              : 'bg-brand-500/10 text-brand-500'
          "
        >
          {{ t(`mods.kinds.${target.data.value.kind}`) }}
        </span>
      </div>
    </header>

    <!-- Unsupported server type -->
    <Card v-if="isUnsupported" class="border-amber-500/30">
      <CardContent class="p-5 flex items-start gap-3">
        <AlertTriangle class="text-amber-500 shrink-0 mt-0.5" :size="20" />
        <div class="space-y-1">
          <div class="font-medium">{{ t('mods.unsupported.title') }}</div>
          <p class="text-sm text-muted-foreground leading-relaxed">
            {{ t('mods.unsupported.desc', { type: target.data.value?.loader_label ?? '?' }) }}
          </p>
        </div>
      </CardContent>
    </Card>

    <!-- Tabs -->
    <div v-if="!isUnsupported" class="flex items-center gap-1 border-b border-border">
      <button
        v-for="key in (['search', 'installed', 'upload'] as const)"
        :key="key"
        type="button"
        class="px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors"
        :class="
          tab === key
            ? 'border-brand-500 text-foreground'
            : 'border-transparent text-muted-foreground hover:text-foreground'
        "
        @click="tab = key"
      >
        {{ t(`mods.tabs.${key}`) }}
        <span
          v-if="key === 'installed' && installed.data.value?.tracked.length"
          class="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-mono bg-accent text-foreground"
        >
          {{ installed.data.value.tracked.length }}
        </span>
      </button>
    </div>

    <!-- SEARCH TAB -->
    <div v-if="!isUnsupported && tab === 'search'" class="space-y-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="relative flex-1 min-w-[280px] max-w-2xl">
          <Search
            :size="16"
            class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
          />
          <Input
            v-model="searchInput"
            type="search"
            :placeholder="t('mods.searchPlaceholder', { source: target.data.value?.loader_label ?? '' })"
            class="pl-9 h-10"
            autofocus
          />
          <span
            v-if="search.isFetching.value && searchInput.length >= 2"
            class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          >
            <Loader2 class="animate-spin" :size="14" />
          </span>
        </div>

        <label
          v-if="target.data.value?.mc_version"
          class="inline-flex items-center gap-2 text-xs text-muted-foreground select-none cursor-pointer"
          :title="t('mods.strictTooltip', { v: target.data.value.mc_version })"
        >
          <input
            v-model="strictVersion"
            type="checkbox"
            class="size-3.5 rounded border-border bg-background accent-brand-500"
          />
          <span>
            {{ t('mods.strictLabel', { v: target.data.value.mc_version }) }}
          </span>
        </label>
      </div>

      <!-- Conflict-risk advisory (mod-kind servers only) -->
      <div
        v-if="target.data.value?.kind === 'mod' && searchInput.length >= 2"
        class="rounded-lg border border-border bg-card/40 backdrop-blur p-3 flex items-start gap-2.5 text-xs leading-relaxed"
      >
        <Info :size="14" class="text-brand-500 shrink-0 mt-0.5" />
        <div class="space-y-1">
          <div class="font-medium text-foreground">
            {{ t('mods.conflictAdvisory.title') }}
          </div>
          <div class="text-muted-foreground">
            {{ t('mods.conflictAdvisory.body') }}
          </div>
        </div>
      </div>

      <!-- Provider errors banner -->
      <div
        v-if="(search.data.value?.providers_errored?.length ?? 0) > 0"
        class="text-xs text-amber-500 inline-flex items-center gap-1.5"
      >
        <AlertTriangle :size="12" />
        {{
          t('mods.providerErrored', {
            list: search.data.value!.providers_errored.map((e) => e.provider).join(', '),
          })
        }}
      </div>

      <!-- Initial state — no query yet -->
      <EmptyState
        v-if="searchInput.length < 2"
        :icon="Search"
        :title="t('mods.idleTitle')"
        :description="t('mods.idleDesc', { source: target.data.value?.loader_label ?? '' })"
      />

      <!-- Loading -->
      <div
        v-else-if="search.isPending.value && !search.data.value"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        <div
          v-for="i in 6"
          :key="i"
          class="h-[140px] rounded-xl border border-border bg-muted/30 animate-pulse"
        />
      </div>

      <!-- Results grid -->
      <div
        v-else-if="search.data.value && search.data.value.hits.length > 0"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        <article
          v-for="hit in search.data.value.hits"
          :key="`${hit.provider}-${hit.project_id}`"
          class="group rounded-xl border bg-card/40 backdrop-blur p-4 flex flex-col gap-3 transition-colors"
          :class="
            isModpack(hit)
              ? 'border-brand-500/40 hover:border-brand-500/70'
              : 'border-border hover:border-brand-500/50'
          "
        >
          <div class="flex items-start gap-3 min-w-0">
            <ProjectIcon :url="hit.icon_url" :alt="hit.title" size="md" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 min-w-0 flex-wrap">
                <h3 class="font-medium text-sm truncate flex-1 min-w-0">{{ hit.title }}</h3>
                <span
                  v-if="isModpack(hit)"
                  class="inline-flex items-center gap-0.5 text-[9px] font-mono px-1.5 py-0.5 rounded bg-brand-500/15 text-brand-500 uppercase shrink-0"
                >
                  <Boxes :size="10" />
                  {{ t('mods.types.modpack') }}
                </span>
                <span
                  class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-accent/60 text-muted-foreground uppercase shrink-0"
                >
                  {{ providerLabel[hit.provider] }}
                </span>
              </div>
              <div class="text-[11px] text-muted-foreground mt-0.5 inline-flex items-center gap-2 flex-wrap">
                <span class="inline-flex items-center gap-0.5">
                  <Download :size="10" />
                  {{ fmtDownloads(hit.downloads) }}
                </span>
                <span v-if="hit.follows" class="inline-flex items-center gap-0.5">
                  <Users :size="10" />
                  {{ fmtDownloads(hit.follows) }}
                </span>
                <!--
                  We only flag *clear* incompatibilities (the user's MC
                  version isn't anywhere in the project's metadata). A
                  green "✓ compatible" badge would over-promise: the
                  project may list 1.21.1 because *some* loader has it,
                  while the user's loader maxes out earlier — install
                  would then fail. The install endpoint itself is the
                  source of truth.
                -->
                <span
                  v-if="compatStatus(hit) === 'mismatch'"
                  class="inline-flex items-center gap-0.5 text-amber-500"
                  :title="compatTooltip(hit)"
                >
                  <AlertTriangle :size="10" />
                  {{ mismatchLabel(hit) }}
                </span>
              </div>
            </div>
          </div>

          <p class="text-xs text-muted-foreground line-clamp-2 leading-relaxed flex-1">
            {{ hit.summary || '—' }}
          </p>

          <div class="flex items-center gap-2">
            <a
              :href="hit.project_url"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex h-7 px-2 items-center gap-1 text-[11px] rounded-md border border-border text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-colors"
            >
              <ExternalLink :size="11" />
              {{ t('mods.view') }}
            </a>
            <!-- Modpack: install disabled with explanation -->
            <a
              v-if="isModpack(hit)"
              :href="hit.project_url"
              target="_blank"
              rel="noopener noreferrer"
              class="ml-auto inline-flex h-7 px-3 items-center gap-1 text-[11px] rounded-md bg-brand-500/15 text-brand-500 hover:bg-brand-500/25 transition-colors font-medium"
              :title="t('mods.modpackInstallDisabled')"
            >
              <ExternalLink :size="11" />
              {{ t('mods.modpackOpen') }}
            </a>
            <Button
              v-else-if="!isInstalled(hit) && compatStatus(hit) !== 'mismatch'"
              size="sm"
              class="ml-auto h-7"
              :disabled="installingId === `${hit.provider}:${hit.project_id}` || install.isPending.value"
              @click="onInstall(hit)"
            >
              <Loader2
                v-if="installingId === `${hit.provider}:${hit.project_id}`"
                class="animate-spin"
                :size="12"
              />
              <Download v-else :size="12" />
              {{
                installingId === `${hit.provider}:${hit.project_id}`
                  ? t('mods.installing')
                  : t('mods.install')
              }}
            </Button>
            <span
              v-else-if="!isInstalled(hit) && compatStatus(hit) === 'mismatch'"
              class="ml-auto inline-flex items-center gap-1 h-7 px-2.5 text-[11px] rounded-md bg-amber-500/10 text-amber-500 cursor-not-allowed"
              :title="compatTooltip(hit)"
            >
              <AlertTriangle :size="12" />
              {{ t('mods.installBlocked') }}
            </span>
            <span
              v-else
              class="ml-auto inline-flex items-center gap-1 text-[11px] text-emerald-500 font-medium"
            >
              <Check :size="12" />
              {{ t('mods.installed') }}
            </span>
          </div>
        </article>
      </div>

      <!-- No results -->
      <div
        v-else-if="search.data.value && search.data.value.hits.length === 0"
        class="space-y-4"
      >
        <EmptyState
          :icon="FileQuestion"
          :title="t('mods.emptyTitle')"
          :description="t('mods.emptyDesc', { q: searchInput })"
        />
        <div class="flex justify-center">
          <Button
            v-if="strictVersion && target.data.value?.mc_version"
            type="button"
            variant="outline"
            size="sm"
            @click="strictVersion = false"
          >
            {{ t('mods.broadenVersion', { v: target.data.value.mc_version }) }}
          </Button>
        </div>
      </div>

    </div>

    <!-- INSTALLED TAB -->
    <div v-if="!isUnsupported && tab === 'installed'" class="space-y-4">
      <div
        v-if="installed.isPending.value && !installed.data.value"
        class="text-sm text-muted-foreground"
      >
        <Loader2 class="inline-block animate-spin mr-2" :size="14" />
        {{ t('common.loading') }}
      </div>

      <EmptyState
        v-else-if="!installed.data.value?.tracked.length"
        :icon="Package"
        :title="t('mods.installedEmpty')"
        :description="t('mods.installedEmptyHint')"
      />

      <div v-else class="space-y-2">
        <div
          v-for="m in installed.data.value!.tracked"
          :key="m.id"
          class="flex items-center gap-3 p-3 rounded-lg border border-border bg-card/40 backdrop-blur"
        >
          <ProjectIcon :url="m.icon_url" :alt="m.title" size="sm" />
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 min-w-0">
              <span class="text-sm font-medium truncate">{{ m.title }}</span>
              <span
                class="text-[9px] font-mono px-1.5 py-0.5 rounded bg-accent/60 text-muted-foreground uppercase shrink-0"
              >
                {{ providerLabel[m.provider] }}
              </span>
              <span
                v-if="!m.present_on_disk"
                class="inline-flex items-center gap-0.5 text-[10px] text-amber-500"
                :title="t('mods.missingOnDisk')"
              >
                <AlertTriangle :size="10" />
                {{ t('mods.missingOnDisk') }}
              </span>
            </div>
            <div class="text-[11px] text-muted-foreground font-mono truncate">
              {{ m.filename }} · {{ fmtSize(m.file_size) }}
              <span v-if="m.version_number"> · v{{ m.version_number }}</span>
            </div>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            class="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
            :disabled="uninstall.isPending.value"
            :title="t('mods.uninstall')"
            @click="onUninstall(m)"
          >
            <Trash2 :size="14" />
          </Button>
        </div>
      </div>

      <!-- Untracked jars warning -->
      <div
        v-if="installed.data.value && installed.data.value.untracked.length > 0"
        class="rounded-xl border border-border bg-card/40 backdrop-blur p-4 space-y-2"
      >
        <div class="flex items-center gap-2 text-xs text-muted-foreground uppercase tracking-wider">
          <FileQuestion :size="12" />
          {{ t('mods.untrackedTitle', { n: installed.data.value.untracked.length }) }}
        </div>
        <p class="text-xs text-muted-foreground leading-relaxed">
          {{ t('mods.untrackedHint') }}
        </p>
        <ul class="space-y-1 font-mono text-[11px] text-muted-foreground">
          <li v-for="j in installed.data.value.untracked" :key="`${j.folder}/${j.filename}`">
            <span class="text-muted-foreground/60">{{ j.folder }}/</span>{{ j.filename }}
            <span class="text-muted-foreground/60"> · {{ fmtSize(j.size) }}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- UPLOAD TAB ============================================== -->
    <div v-if="!isUnsupported && tab === 'upload'" class="space-y-5">
      <!-- Curated upstream sources -->
      <div class="space-y-2">
        <div class="text-xs uppercase tracking-wider text-muted-foreground font-medium">
          {{ t('mods.manual.sourcesHeader') }}
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <a
            v-for="s in sources"
            :key="s.id"
            :href="s.url"
            target="_blank"
            rel="noopener noreferrer"
            class="group flex flex-col gap-1 rounded-lg border border-border bg-card/40 backdrop-blur p-3 hover:border-brand-500/60 hover:bg-accent/40 transition-colors"
          >
            <div class="flex items-center justify-between">
              <span class="text-sm font-medium">{{ s.label }}</span>
              <ExternalLink :size="12" class="text-muted-foreground group-hover:text-brand-500" />
            </div>
            <div class="text-[10px] text-muted-foreground">{{ s.host }}</div>
            <div class="text-[10px] text-muted-foreground/70 leading-snug">{{ s.tag }}</div>
          </a>
        </div>
      </div>

      <!-- Drop zone -->
      <div class="rounded-xl border border-border bg-card/40 backdrop-blur p-5 space-y-4">
        <div class="flex items-start gap-3">
          <Upload :size="20" class="text-brand-500 shrink-0 mt-0.5" />
          <div class="space-y-1 flex-1 min-w-0">
            <h3 class="font-medium">{{ t('mods.manual.title') }}</h3>
            <p class="text-xs text-muted-foreground leading-relaxed">
              {{ t('mods.manual.subtitle') }}
            </p>
          </div>
        </div>

        <input
          ref="uploadInputRef"
          type="file"
          accept=".jar,.mrpack,.zip"
          class="hidden"
          @change="onUploadFileChange"
        />

        <!-- Empty state: pick a file -->
        <button
          v-if="!uploadFile"
          type="button"
          class="w-full border-2 border-dashed border-border rounded-lg py-10 px-4 text-center hover:border-brand-500/60 hover:bg-accent/30 transition-colors"
          @click="pickUploadFile"
        >
          <Upload :size="24" class="mx-auto text-muted-foreground" />
          <div class="text-sm font-medium mt-2">{{ t('mods.manual.pickFile') }}</div>
          <div class="text-[11px] text-muted-foreground mt-1">{{ t('mods.manual.pickHint') }}</div>
        </button>

        <!-- File selected: inspection result + install action -->
        <div v-else class="space-y-3">
          <!-- Filename + clear -->
          <div class="flex items-center gap-2">
            <Package :size="16" class="text-muted-foreground" />
            <span class="font-mono text-sm truncate flex-1">{{ uploadFile.name }}</span>
            <span class="text-[11px] text-muted-foreground">{{ fmtSize(uploadFile.size) }}</span>
            <button
              type="button"
              class="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              :title="t('common.clear')"
              @click="resetUpload"
            >
              <X :size="14" />
            </button>
          </div>

          <!-- Inspecting -->
          <div
            v-if="inspectUpload.isPending.value"
            class="flex items-center gap-2 text-xs text-muted-foreground"
          >
            <Loader2 class="animate-spin" :size="12" />
            {{ t('mods.manual.inspecting') }}
          </div>

          <!-- Inspection result -->
          <div
            v-else-if="uploadInspect"
            class="rounded-lg border border-border bg-background/40 p-3 space-y-2.5"
          >
            <!-- Identity -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div>
                <span class="text-muted-foreground">{{ t('mods.manual.detectedKind') }}: </span>
                <span class="font-medium">
                  {{ t(`mods.kinds.${uploadInspect.meta.kind === 'unknown' ? 'mod' : uploadInspect.meta.kind}`) }}
                </span>
              </div>
              <div v-if="uploadInspect.meta.loaders.length">
                <span class="text-muted-foreground">{{ t('mods.manual.loader') }}: </span>
                <span class="font-medium">{{ uploadInspect.meta.loaders.join(', ') }}</span>
              </div>
              <div v-if="uploadInspect.meta.name">
                <span class="text-muted-foreground">{{ t('mods.manual.name') }}: </span>
                <span class="font-medium">{{ uploadInspect.meta.name }}</span>
              </div>
              <div v-if="uploadInspect.meta.version">
                <span class="text-muted-foreground">{{ t('mods.manual.version') }}: </span>
                <span class="font-mono">{{ uploadInspect.meta.version }}</span>
              </div>
              <div v-if="uploadInspect.meta.mc_version_range" class="sm:col-span-2">
                <span class="text-muted-foreground">{{ t('mods.manual.mcRange') }}: </span>
                <span class="font-mono">{{ uploadInspect.meta.mc_version_range }}</span>
              </div>
            </div>

            <!-- Verdict badges -->
            <div class="flex flex-wrap gap-3 pt-1 border-t border-border text-xs">
              <span class="inline-flex items-center gap-1" :class="verdictColor(uploadInspect.verdict.loader)">
                <ShieldCheck v-if="uploadInspect.verdict.loader === 'ok'" :size="12" />
                <AlertTriangle v-else-if="uploadInspect.verdict.loader === 'mismatch'" :size="12" />
                <Info v-else :size="12" />
                {{ t(`mods.manual.verdict.loader.${uploadInspect.verdict.loader}`, {
                  expected: uploadInspect.target.loader_label,
                }) }}
              </span>
              <span class="inline-flex items-center gap-1" :class="verdictColor(uploadInspect.verdict.mc)">
                <ShieldCheck v-if="uploadInspect.verdict.mc === 'ok'" :size="12" />
                <AlertTriangle v-else-if="uploadInspect.verdict.mc === 'mismatch'" :size="12" />
                <Info v-else :size="12" />
                {{ t(`mods.manual.verdict.mc.${uploadInspect.verdict.mc}`, {
                  current: uploadInspect.target.mc_version,
                }) }}
              </span>
            </div>

            <!-- Block reason when we know we can't install (modpack, unknown) -->
            <div
              v-if="!uploadInspect.meta.can_install"
              class="rounded-md border border-amber-500/30 bg-amber-500/10 p-2.5 flex items-start gap-2 text-xs"
            >
              <AlertTriangle :size="13" class="text-amber-500 shrink-0 mt-0.5" />
              <div>
                <div class="font-medium">{{ t('mods.manual.cantInstall') }}</div>
                <p class="text-muted-foreground mt-0.5">
                  {{ uploadInspect.meta.install_reason }}
                </p>
              </div>
            </div>

            <!-- Kind picker when we couldn't tell -->
            <div
              v-if="uploadInspect.meta.kind === 'unknown' && uploadInspect.meta.can_install"
              class="space-y-1.5 pt-1 border-t border-border"
            >
              <div class="text-xs text-muted-foreground">
                {{ t('mods.manual.pickKindPrompt') }}
              </div>
              <div class="flex gap-2">
                <Button
                  v-for="k in (['mod', 'plugin'] as const)"
                  :key="k"
                  type="button"
                  size="sm"
                  :variant="forceKind === k ? 'default' : 'outline'"
                  @click="forceKind = k"
                >
                  {{ t(`mods.kinds.${k}`) }}
                </Button>
              </div>
            </div>
          </div>

          <!-- Install action -->
          <div class="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              :disabled="
                !uploadInspect ||
                uploadInstall.isPending.value ||
                (uploadInspect.meta.can_install === false) ||
                (uploadInspect.meta.kind === 'unknown' && !forceKind)
              "
              :variant="uploadInspect?.verdict.overall === 'warn' ? 'destructive' : 'default'"
              @click="commitUpload"
            >
              <Loader2 v-if="uploadInstall.isPending.value" class="animate-spin" :size="14" />
              <Upload v-else :size="14" />
              {{
                uploadInspect?.verdict.overall === 'warn'
                  ? t('mods.manual.installAnyway')
                  : t('mods.manual.install')
              }}
            </Button>
            <span
              v-if="uploadInspect?.verdict.overall === 'warn'"
              class="text-[11px] text-amber-500"
            >
              {{ t('mods.manual.warnNote') }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
