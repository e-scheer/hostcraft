<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CalendarClock,
  Loader2,
  Pencil,
  Play,
  Plus,
  Trash2,
  TriangleAlert,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  CRON_PRESETS,
  useScheduleActions,
  useSchedulesList,
} from '@/composables/useSchedules'
import { formatRelativeTime } from '@/composables/useFiles'
import type { Schedule, ScheduleKind, SchedulePayload } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const dialog = useDialogStore()
const list = useSchedulesList()
const actions = useScheduleActions()

const KINDS: { value: ScheduleKind; label: string; description: string }[] = [
  { value: 'restart', label: t('schedules.kinds.restart'), description: t('schedules.kinds.restartHelp') },
  { value: 'backup_world', label: t('schedules.kinds.backup_world'), description: t('schedules.kinds.backupWorldHelp') },
  { value: 'backup_full', label: t('schedules.kinds.backup_full'), description: t('schedules.kinds.backupFullHelp') },
  { value: 'rcon', label: t('schedules.kinds.rcon'), description: t('schedules.kinds.rconHelp') },
]

const formOpen = ref(false)
const editingId = ref<number | null>(null)

interface FormState {
  name: string
  kind: ScheduleKind
  cron: string
  enabled: boolean
  command: string
  namePrefix: string
}

const form = ref<FormState>({
  name: '',
  kind: 'restart',
  cron: '0 4 * * *',
  enabled: true,
  command: '',
  namePrefix: '',
})

function resetForm() {
  form.value = {
    name: '',
    kind: 'restart',
    cron: '0 4 * * *',
    enabled: true,
    command: '',
    namePrefix: '',
  }
  editingId.value = null
}

function openCreate() {
  resetForm()
  formOpen.value = true
}

function openEdit(s: Schedule) {
  form.value = {
    name: s.name,
    kind: s.kind,
    cron: s.cron,
    enabled: s.enabled,
    command: String(s.payload?.command ?? ''),
    namePrefix: String(s.payload?.name_prefix ?? ''),
  }
  editingId.value = s.id
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  resetForm()
}

function buildPayload(): SchedulePayload {
  const payload: Record<string, unknown> = {}
  if (form.value.kind === 'rcon') payload.command = form.value.command
  if (form.value.kind === 'backup_world' || form.value.kind === 'backup_full') {
    if (form.value.namePrefix.trim()) payload.name_prefix = form.value.namePrefix.trim()
  }
  return {
    name: form.value.name.trim(),
    kind: form.value.kind,
    cron: form.value.cron.trim(),
    enabled: form.value.enabled,
    payload,
  }
}

const formValid = computed(() => {
  if (!form.value.name.trim() || !form.value.cron.trim()) return false
  if (form.value.kind === 'rcon' && !form.value.command.trim()) return false
  return true
})

function onSubmit() {
  if (!formValid.value) return
  const data = buildPayload()
  if (editingId.value != null) {
    actions.update.mutate(
      { id: editingId.value, data },
      { onSuccess: closeForm },
    )
  } else {
    actions.create.mutate(data, { onSuccess: closeForm })
  }
}

async function onDelete(s: Schedule) {
  const ok = await dialog.confirm({
    title: t('schedules.confirmDelete', { name: s.name }),
    confirmLabel: t('common.delete'),
    variant: 'destructive',
  })
  if (!ok) return
  actions.remove.mutate(s)
}

function onToggleEnabled(s: Schedule, enabled: boolean) {
  actions.update.mutate({ id: s.id, data: { enabled } })
}

function onRunNow(s: Schedule) {
  actions.runNow.mutate(s)
}

function statusBadgeClass(st: string): string {
  switch (st) {
    case 'success':
      return 'bg-brand-700/20 text-brand-300 border-brand-700/40'
    case 'running':
      return 'bg-amber-400/10 text-amber-300 border-amber-400/30'
    case 'failed':
      return 'bg-destructive/10 text-destructive border-destructive/30'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}

function unixOf(iso: string | null): number {
  return iso ? Math.floor(new Date(iso).getTime() / 1000) : 0
}

watch(
  () => form.value.kind,
  () => {
    // Clear kind-specific fields when switching kinds.
    if (form.value.kind !== 'rcon') form.value.command = ''
    if (form.value.kind !== 'backup_world' && form.value.kind !== 'backup_full') {
      form.value.namePrefix = ''
    }
  },
)
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div class="space-y-1">
        <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <CalendarClock :size="22" class="text-brand-500" />
          {{ t('schedules.title') }}
        </h2>
        <p class="text-sm text-muted-foreground">{{ t('schedules.subtitle') }}</p>
      </div>
      <Button size="sm" @click="openCreate">
        <Plus />
        {{ t('schedules.create') }}
      </Button>
    </header>

    <!-- Form -->
    <Transition name="view-fade">
      <Card v-if="formOpen">
        <CardContent class="p-5 space-y-4">
          <!-- Kind -->
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <button
              v-for="k in KINDS"
              :key="k.value"
              type="button"
              class="flex flex-col gap-1 rounded-lg border p-3 text-left transition-colors"
              :class="
                form.kind === k.value
                  ? 'border-brand-500 bg-brand-500/5'
                  : 'border-border hover:bg-accent/40'
              "
              @click="form.kind = k.value"
            >
              <span class="text-sm font-medium">{{ k.label }}</span>
              <span class="text-xs text-muted-foreground leading-snug">{{ k.description }}</span>
            </button>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <div class="space-y-1.5">
              <Label for="sched-name">{{ t('common.name') }}</Label>
              <Input
                id="sched-name"
                v-model="form.name"
                :placeholder="t('schedules.namePlaceholder')"
                autocomplete="off"
              />
            </div>
            <div class="space-y-1.5">
              <Label for="sched-cron">{{ t('schedules.cron') }}</Label>
              <Input id="sched-cron" v-model="form.cron" placeholder="0 4 * * *" class="font-mono" />
              <div class="flex flex-wrap gap-1 pt-1">
                <button
                  v-for="p in CRON_PRESETS"
                  :key="p.cron"
                  type="button"
                  class="text-[11px] rounded-md border border-border px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :class="form.cron === p.cron ? 'border-brand-500/60 bg-brand-500/10 text-brand-300' : ''"
                  @click="form.cron = p.cron"
                >
                  {{ p.label }}
                </button>
              </div>
            </div>
          </div>

          <!-- Kind-specific -->
          <div v-if="form.kind === 'rcon'" class="space-y-1.5">
            <Label for="sched-cmd">{{ t('schedules.fields.command') }}</Label>
            <Input
              id="sched-cmd"
              v-model="form.command"
              placeholder="say Server reboot in 5 minutes"
              class="font-mono"
            />
          </div>

          <div
            v-if="form.kind === 'backup_world' || form.kind === 'backup_full'"
            class="space-y-1.5"
          >
            <Label for="sched-prefix">{{ t('schedules.fields.namePrefix') }}</Label>
            <Input id="sched-prefix" v-model="form.namePrefix" placeholder="nightly" />
          </div>

          <div class="flex items-center gap-2.5">
            <Switch v-model="form.enabled" />
            <Label class="text-sm">{{ t('schedules.fields.enabled') }}</Label>
          </div>

          <div class="flex justify-end gap-2 pt-2">
            <Button variant="ghost" size="sm" @click="closeForm">
              {{ t('common.cancel') }}
            </Button>
            <Button
              size="sm"
              :disabled="!formValid || actions.create.isPending.value || actions.update.isPending.value"
              @click="onSubmit"
            >
              <Loader2
                v-if="actions.create.isPending.value || actions.update.isPending.value"
                class="animate-spin"
              />
              <Plus v-else />
              {{
                editingId != null
                  ? t('common.save')
                  : t('schedules.create')
              }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </Transition>

    <!-- List -->
    <div class="rounded-xl border border-border bg-card overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th class="px-3 py-2 text-left font-medium">{{ t('common.name') }}</th>
            <th class="px-3 py-2 text-left font-medium hidden sm:table-cell">{{ t('schedules.headers.kind') }}</th>
            <th class="px-3 py-2 text-left font-medium font-mono hidden md:table-cell">{{ t('schedules.cron') }}</th>
            <th class="px-3 py-2 text-left font-medium hidden lg:table-cell">{{ t('schedules.headers.next') }}</th>
            <th class="px-3 py-2 text-left font-medium hidden lg:table-cell">{{ t('schedules.headers.lastRun') }}</th>
            <th class="px-3 py-2 text-left font-medium">{{ t('schedules.headers.status') }}</th>
            <th class="px-3 py-2 text-left font-medium">{{ t('schedules.headers.enabled') }}</th>
            <th class="w-32 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-if="list.isPending.value && !list.data.value">
            <td colspan="8" class="px-4 py-8 text-center text-muted-foreground">
              {{ t('common.loading') }}
            </td>
          </tr>
          <tr v-else-if="!list.data.value?.length">
            <td colspan="8" class="px-4 py-12 text-center text-muted-foreground">
              <div class="text-base font-medium mb-1">{{ t('schedules.empty') }}</div>
              <div class="text-xs">{{ t('schedules.emptyHint') }}</div>
            </td>
          </tr>
          <tr
            v-for="s in list.data.value ?? []"
            :key="s.id"
            class="border-t border-border hover:bg-accent/30 transition-colors"
          >
            <td class="px-3 py-2">
              <div class="font-medium truncate">{{ s.name }}</div>
              <div
                v-if="s.last_status === 'failed'"
                class="text-xs text-destructive flex items-center gap-1 mt-0.5"
              >
                <TriangleAlert :size="12" />
                <span class="truncate">{{ s.last_error.split('\n')[0] }}</span>
              </div>
            </td>
            <td class="px-3 py-2 hidden sm:table-cell">
              <span class="text-xs font-mono text-muted-foreground">{{ s.kind }}</span>
            </td>
            <td class="px-3 py-2 font-mono text-xs text-muted-foreground hidden md:table-cell">
              {{ s.cron }}
            </td>
            <td class="px-3 py-2 text-xs text-muted-foreground hidden lg:table-cell">
              <template v-if="s.next_run_at">
                {{ formatRelativeTime(unixOf(s.next_run_at)) }}
              </template>
              <span v-else>—</span>
            </td>
            <td class="px-3 py-2 text-xs text-muted-foreground hidden lg:table-cell">
              <template v-if="s.last_run_at">
                {{ formatRelativeTime(unixOf(s.last_run_at)) }}
              </template>
              <span v-else>—</span>
            </td>
            <td class="px-3 py-2">
              <span
                class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium"
                :class="statusBadgeClass(s.last_status)"
              >
                <Loader2 v-if="s.last_status === 'running'" class="animate-spin" :size="10" />
                {{ t(`schedules.statuses.${s.last_status}`) }}
              </span>
            </td>
            <td class="px-3 py-2">
              <Switch :model-value="s.enabled" @update:model-value="onToggleEnabled(s, $event)" />
            </td>
            <td class="px-3 py-2">
              <div class="flex items-center justify-end gap-1">
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :aria-label="t('schedules.runNow')"
                  :title="t('schedules.runNow')"
                  @click="onRunNow(s)"
                >
                  <Play :size="14" />
                </button>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :aria-label="t('common.edit')"
                  :title="t('common.edit')"
                  @click="openEdit(s)"
                >
                  <Pencil :size="14" />
                </button>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                  :aria-label="t('common.delete')"
                  :title="t('common.delete')"
                  @click="onDelete(s)"
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
