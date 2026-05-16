<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Archive,
  CloudUpload,
  Download,
  Loader2,
  Plus,
  RotateCcw,
  Trash2,
  TriangleAlert,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useBackupActions,
  useBackupSizes,
  useBackupSummary,
  useBackupsList,
  useDestinations,
  useRestoreBackup,
  useUploadBackup,
} from '@/composables/useBackups'
import {
  downloadAuthenticated,
  type BackupDestination,
  type BackupEntry,
  type BackupKind,
} from '@/lib/api'
import { formatBytes, formatRelativeTime } from '@/composables/useFiles'
import { useDialogStore } from '@/stores/dialog'
import BackupDestinationsPanel from '@/components/BackupDestinationsPanel.vue'

const { t } = useI18n()
const dialog = useDialogStore()

type Tab = 'backups' | 'destinations'
const tab = ref<Tab>('backups')

const list = useBackupsList()
const actions = useBackupActions()
const summary = useBackupSummary(() => list.data.value)
const destinations = useDestinations()
const uploader = useUploadBackup()
const restorer = useRestoreBackup()

const formOpen = ref(false)
// Pass formOpen so the size query auto-polls (5s) only when the form is open.
const sizes = useBackupSizes(formOpen)
const formKind = ref<BackupKind>('world')
const formName = ref('')

function onCreate() {
  actions.create.mutate(
    { kind: formKind.value, name: formName.value.trim() || undefined },
    {
      onSuccess: () => {
        formOpen.value = false
        formName.value = ''
      },
    },
  )
}

async function onDelete(entry: BackupEntry) {
  const ok = await dialog.confirm({
    title: t('backups.confirmDelete', { name: entry.name }),
    confirmLabel: t('common.delete'),
    variant: 'destructive',
  })
  if (!ok) return
  actions.remove.mutate(entry)
}

function onDownload(entry: BackupEntry) {
  downloadAuthenticated(`backups/${entry.id}/download/`, `${entry.name}.tar.gz`)
}

async function onRestore(entry: BackupEntry) {
  const ok = await dialog.confirm({
    title: t('backups.confirmRestoreTitle', { name: entry.name }),
    description: t('backups.confirmRestoreDesc'),
    confirmLabel: t('backups.restoreAction'),
    variant: 'destructive',
  })
  if (!ok) return
  restorer.mutate(entry)
}

async function onUpload(entry: BackupEntry) {
  const enabled = (destinations.data.value ?? []).filter((d) => d.enabled)
  if (enabled.length === 0) {
    toast.error(t('backups.toasts.noDestination'), {
      description: t('backups.toasts.noDestinationDesc'),
    })
    return
  }
  // 1 destination → upload directly. 2+ → ask which.
  let target: BackupDestination | undefined = enabled[0]
  if (enabled.length > 1) {
    const labels = enabled.map((d) => `• ${d.name}  (${d.bucket})`).join('\n')
    const ok = await dialog.confirm({
      title: t('backups.uploadPickTitle'),
      description: `${t('backups.uploadPickDesc')}\n\n${labels}\n\n${t('backups.uploadPickHint')}`,
      confirmLabel: enabled[0].name,
    })
    if (!ok) return
    target = enabled[0]
  }
  if (!target) return
  uploader.mutate({ backup: entry, destination: target })
}

const remoteBadgeClass = (rs: string): string => {
  switch (rs) {
    case 'uploaded': return 'bg-brand-700/20 text-brand-300 border-brand-700/40'
    case 'uploading':
    case 'pending': return 'bg-amber-400/10 text-amber-300 border-amber-400/30'
    case 'failed': return 'bg-destructive/10 text-destructive border-destructive/30'
    default: return 'hidden'
  }
}

// late import to avoid hoisting drama
import { toast } from 'vue-sonner'

function unixOf(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000)
}

const statusBadgeClass = computed(() => (status: string) => {
  switch (status) {
    case 'ready':
      return 'bg-brand-700/20 text-brand-300 border-brand-700/40'
    case 'running':
      return 'bg-amber-400/10 text-amber-300 border-amber-400/30'
    case 'pending':
      return 'bg-muted text-muted-foreground border-border'
    case 'failed':
      return 'bg-destructive/10 text-destructive border-destructive/30'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
})
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div class="space-y-1">
        <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Archive
            :size="22"
            class="text-brand-500"
          />
          {{ t('backups.title') }}
        </h2>
        <p class="text-sm text-muted-foreground">
          {{ t('backups.subtitle') }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <span
          v-if="tab === 'backups'"
          class="text-xs text-muted-foreground tabular-nums"
        >
          {{
            t('backups.summary', {
              ready: summary.ready,
              inFlight: summary.inFlight,
              size: formatBytes(summary.totalSize),
            })
          }}
        </span>
        <Button
          v-if="tab === 'backups'"
          size="sm"
          @click="formOpen = !formOpen"
        >
          <Plus />
          {{ t('backups.create') }}
        </Button>
      </div>
    </header>

    <div
      role="tablist"
      class="inline-flex rounded-lg border border-border bg-card p-1 gap-1"
    >
      <button
        v-for="key in (['backups', 'destinations'] as const)"
        :key="key"
        type="button"
        role="tab"
        class="px-4 py-1.5 text-sm font-medium rounded-md transition-colors"
        :class="
          tab === key ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'
        "
        @click="tab = key"
      >
        {{ t(`backups.tabs.${key}`) }}
      </button>
    </div>

    <BackupDestinationsPanel v-if="tab === 'destinations'" />

    <!-- Create form -->
    <Transition
      v-if="tab === 'backups'"
      name="view-fade"
    >
      <Card v-if="formOpen">
        <CardContent class="p-5 space-y-4">
          <div class="grid gap-3 sm:grid-cols-2">
            <button
              v-for="kind in (['world', 'full'] as const)"
              :key="kind"
              type="button"
              class="flex flex-col gap-1.5 rounded-lg border p-4 text-left transition-colors"
              :class="
                formKind === kind
                  ? 'border-brand-500 bg-brand-500/5'
                  : 'border-border hover:bg-accent/40'
              "
              @click="formKind = kind"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-medium">{{ t(`backups.kinds.${kind}`) }}</span>
                <span
                  class="text-[11px] font-mono tabular-nums px-2 py-0.5 rounded-full bg-muted text-muted-foreground shrink-0"
                >
                  {{
                    sizes.data.value
                      ? t('backups.kinds.estimate', {
                        size: formatBytes(sizes.data.value[kind] ?? 0),
                      })
                      : t('backups.kinds.estimateLoading')
                  }}
                </span>
              </div>
              <span class="text-xs text-muted-foreground">
                {{ t(`backups.kinds.${kind}_help`) }}
              </span>
            </button>
          </div>
          <p class="text-[11px] text-muted-foreground italic">
            {{ t('backups.kinds.compressionNote') }}
          </p>

          <div class="space-y-1.5">
            <Label for="bk-name">{{ t('common.name') }}</Label>
            <Input
              id="bk-name"
              v-model="formName"
              :placeholder="`${formKind}-2026-05-03-…`"
              autocomplete="off"
            />
          </div>
          <div class="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              @click="formOpen = false"
            >
              {{ t('common.cancel') }}
            </Button>
            <Button
              size="sm"
              :disabled="actions.create.isPending.value"
              @click="onCreate"
            >
              <Loader2
                v-if="actions.create.isPending.value"
                class="animate-spin"
              />
              <Plus v-else />
              {{ actions.create.isPending.value ? t('backups.creating') : t('backups.create') }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </Transition>

    <!-- List -->
    <div
      v-if="tab === 'backups'"
      class="rounded-xl border border-border bg-card overflow-hidden"
    >
      <table class="w-full text-sm">
        <thead class="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th class="px-3 py-2 text-left font-medium">
              {{ t('backups.headers.name') }}
            </th>
            <th class="px-3 py-2 text-left font-medium hidden sm:table-cell">
              {{ t('backups.headers.kind') }}
            </th>
            <th class="px-3 py-2 text-right font-medium hidden sm:table-cell">
              {{ t('backups.headers.size') }}
            </th>
            <th class="px-3 py-2 text-left font-medium hidden md:table-cell">
              {{ t('backups.headers.created') }}
            </th>
            <th class="px-3 py-2 text-left font-medium">
              {{ t('backups.headers.status') }}
            </th>
            <th class="w-24 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-if="list.isPending.value && !list.data.value">
            <td
              colspan="6"
              class="px-4 py-8 text-center text-muted-foreground"
            >
              {{ t('common.loading') }}
            </td>
          </tr>
          <tr v-else-if="!list.data.value?.length">
            <td
              colspan="6"
              class="px-4 py-12 text-center text-muted-foreground"
            >
              <div class="text-base font-medium mb-1">
                {{ t('backups.empty') }}
              </div>
              <div class="text-xs">
                {{ t('backups.emptyHint') }}
              </div>
            </td>
          </tr>
          <tr
            v-for="entry in list.data.value ?? []"
            :key="entry.id"
            class="border-t border-border hover:bg-accent/30 transition-colors"
          >
            <td class="px-3 py-2">
              <div class="font-medium truncate flex items-center gap-2">
                {{ entry.name }}
                <span
                  v-if="entry.remote_status !== 'none'"
                  class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium"
                  :class="remoteBadgeClass(entry.remote_status)"
                  :title="entry.remote_destination_name"
                >
                  <Loader2
                    v-if="entry.remote_status === 'pending' || entry.remote_status === 'uploading'"
                    class="animate-spin"
                    :size="9"
                  />
                  <CloudUpload
                    v-else
                    :size="10"
                  />
                  {{ t(`backups.remote.${entry.remote_status}`) }}
                </span>
                <span
                  v-if="entry.restore_status === 'running'"
                  class="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-400/10 text-amber-300 px-2 py-0.5 text-[10px] font-medium"
                >
                  <Loader2
                    class="animate-spin"
                    :size="9"
                  />
                  {{ t('backups.restoring') }}
                </span>
              </div>
              <div
                v-if="entry.status === 'failed'"
                class="text-xs text-destructive flex items-center gap-1 mt-0.5"
              >
                <TriangleAlert :size="12" />
                <span class="truncate">{{ entry.error.split('\n')[0] }}</span>
              </div>
              <div
                v-else-if="entry.remote_status === 'failed'"
                class="text-xs text-destructive flex items-center gap-1 mt-0.5"
              >
                <TriangleAlert :size="12" />
                <span class="truncate">{{ entry.remote_error.split('\n')[0] }}</span>
              </div>
              <div
                v-else-if="entry.restore_status === 'failed'"
                class="text-xs text-destructive flex items-center gap-1 mt-0.5"
              >
                <TriangleAlert :size="12" />
                <span class="truncate">{{ entry.restore_error.split('\n')[0] }}</span>
              </div>
            </td>
            <td class="px-3 py-2 hidden sm:table-cell">
              <span class="text-xs font-mono text-muted-foreground">{{ entry.kind }}</span>
            </td>
            <td class="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">
              {{ entry.status === 'ready' ? formatBytes(entry.size_bytes) : '—' }}
            </td>
            <td class="px-3 py-2 text-muted-foreground hidden md:table-cell">
              {{ formatRelativeTime(unixOf(entry.created_at)) }}
            </td>
            <td class="px-3 py-2">
              <span
                class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium"
                :class="statusBadgeClass(entry.status)"
              >
                <Loader2
                  v-if="entry.status === 'running' || entry.status === 'pending'"
                  class="animate-spin"
                  :size="10"
                />
                {{ t(`backups.statuses.${entry.status}`) }}
              </span>
            </td>
            <td class="px-3 py-2">
              <div class="flex items-center justify-end gap-1">
                <button
                  v-if="entry.status === 'ready'"
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
                  :disabled="entry.restore_status === 'running'"
                  :aria-label="t('backups.restoreAction')"
                  :title="t('backups.restoreAction')"
                  @click="onRestore(entry)"
                >
                  <RotateCcw :size="14" />
                </button>
                <button
                  v-if="entry.status === 'ready'"
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
                  :disabled="entry.remote_status === 'pending' || entry.remote_status === 'uploading'"
                  :aria-label="t('backups.uploadAction')"
                  :title="t('backups.uploadAction')"
                  @click="onUpload(entry)"
                >
                  <CloudUpload :size="14" />
                </button>
                <button
                  v-if="entry.status === 'ready'"
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :aria-label="t('common.download')"
                  :title="t('common.download')"
                  @click="onDownload(entry)"
                >
                  <Download :size="14" />
                </button>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors disabled:opacity-50"
                  :disabled="entry.status === 'running'"
                  :aria-label="t('common.delete')"
                  :title="t('common.delete')"
                  @click="onDelete(entry)"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
