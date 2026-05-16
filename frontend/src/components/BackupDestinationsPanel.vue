<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CheckCircle,
  CloudUpload,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  useDestinationActions,
  useDestinations,
} from '@/composables/useBackups'
import type { BackupDestination, BackupDestinationPayload } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const dialog = useDialogStore()
const list = useDestinations()
const actions = useDestinationActions()

const formOpen = ref(false)
const editingId = ref<number | null>(null)

interface FormState {
  name: string
  endpoint_url: string
  bucket: string
  prefix: string
  region: string
  access_key: string
  secret_key: string
  auto_upload: boolean
  enabled: boolean
}

const form = ref<FormState>(initialForm())

function initialForm(): FormState {
  return {
    name: '',
    endpoint_url: '',
    bucket: '',
    prefix: '',
    region: 'us-east-1',
    access_key: '',
    secret_key: '',
    auto_upload: false,
    enabled: true,
  }
}

function openCreate() {
  editingId.value = null
  form.value = initialForm()
  formOpen.value = true
}

function openEdit(d: BackupDestination) {
  editingId.value = d.id
  form.value = {
    name: d.name,
    endpoint_url: d.endpoint_url,
    bucket: d.bucket,
    prefix: d.prefix,
    region: d.region,
    access_key: d.access_key,
    secret_key: '',  // never echoed back; leave blank to keep current
    auto_upload: d.auto_upload,
    enabled: d.enabled,
  }
  formOpen.value = true
}

function closeForm() {
  formOpen.value = false
  editingId.value = null
  form.value = initialForm()
}

const formValid = () =>
  form.value.name.trim() &&
  form.value.bucket.trim() &&
  form.value.access_key.trim() &&
  // On create, secret is required. On edit, blank means "keep current".
  (editingId.value != null || form.value.secret_key.trim())

function buildPayload(): BackupDestinationPayload {
  const data: BackupDestinationPayload = {
    name: form.value.name.trim(),
    endpoint_url: form.value.endpoint_url.trim(),
    bucket: form.value.bucket.trim(),
    prefix: form.value.prefix.trim(),
    region: form.value.region.trim(),
    access_key: form.value.access_key.trim(),
    auto_upload: form.value.auto_upload,
    enabled: form.value.enabled,
  }
  if (form.value.secret_key.trim()) data.secret_key = form.value.secret_key
  return data
}

function onSubmit() {
  if (!formValid()) return
  const data = buildPayload()
  if (editingId.value != null) {
    actions.update.mutate({ id: editingId.value, data }, { onSuccess: closeForm })
  } else {
    actions.create.mutate(data, { onSuccess: closeForm })
  }
}

async function onDelete(d: BackupDestination) {
  const ok = await dialog.confirm({
    title: t('destinations.confirmDelete', { name: d.name }),
    confirmLabel: t('common.delete'),
    variant: 'destructive',
  })
  if (!ok) return
  actions.remove.mutate(d)
}

const PRESETS = [
  { label: 'AWS S3', endpoint: '', region: 'us-east-1' },
  { label: 'Backblaze B2 (us-west-001)', endpoint: 'https://s3.us-west-001.backblazeb2.com', region: 'us-west-001' },
  { label: 'Wasabi (us-east-1)', endpoint: 'https://s3.us-east-1.wasabisys.com', region: 'us-east-1' },
  { label: 'DigitalOcean Spaces (nyc3)', endpoint: 'https://nyc3.digitaloceanspaces.com', region: 'nyc3' },
  { label: 'OVH Object Storage (gra)', endpoint: 'https://s3.gra.io.cloud.ovh.net', region: 'gra' },
  { label: 'MinIO (local)', endpoint: 'http://minio:9000', region: 'us-east-1' },
]

function applyPreset(p: typeof PRESETS[number]) {
  form.value.endpoint_url = p.endpoint
  form.value.region = p.region
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-end justify-between gap-3">
      <p class="text-sm text-muted-foreground">
        {{ t('destinations.subtitle') }}
      </p>
      <Button size="sm" @click="openCreate">
        <Plus />
        {{ t('destinations.create') }}
      </Button>
    </div>

    <!-- Form -->
    <Transition name="view-fade">
      <Card v-if="formOpen">
        <CardContent class="p-5 space-y-4">
          <!-- Provider presets -->
          <div>
            <Label class="text-xs">{{ t('destinations.preset') }}</Label>
            <div class="flex flex-wrap gap-1 pt-1">
              <button
                v-for="p in PRESETS"
                :key="p.label"
                type="button"
                class="text-[11px] rounded-md border border-border px-2 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                @click="applyPreset(p)"
              >
                {{ p.label }}
              </button>
            </div>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <div class="space-y-1.5">
              <Label for="d-name">{{ t('common.name') }}</Label>
              <Input id="d-name" v-model="form.name" :placeholder="t('destinations.namePlaceholder')" />
            </div>
            <div class="space-y-1.5">
              <Label for="d-bucket">{{ t('destinations.bucket') }}</Label>
              <Input id="d-bucket" v-model="form.bucket" placeholder="hostcraft-backups" />
            </div>
            <div class="space-y-1.5 sm:col-span-2">
              <Label for="d-endpoint">{{ t('destinations.endpoint') }}</Label>
              <Input
                id="d-endpoint"
                v-model="form.endpoint_url"
                placeholder="https://s3.us-west-001.backblazeb2.com"
                class="font-mono text-xs"
              />
              <p class="text-[11px] text-muted-foreground">
                {{ t('destinations.endpointHelp') }}
              </p>
            </div>
            <div class="space-y-1.5">
              <Label for="d-region">{{ t('destinations.region') }}</Label>
              <Input id="d-region" v-model="form.region" placeholder="us-east-1" />
            </div>
            <div class="space-y-1.5">
              <Label for="d-prefix">{{ t('destinations.prefix') }}</Label>
              <Input id="d-prefix" v-model="form.prefix" :placeholder="t('destinations.prefixPlaceholder')" />
            </div>
            <div class="space-y-1.5">
              <Label for="d-access">{{ t('destinations.accessKey') }}</Label>
              <Input
                id="d-access"
                v-model="form.access_key"
                autocomplete="off"
                spellcheck="false"
                class="font-mono text-xs"
              />
            </div>
            <div class="space-y-1.5">
              <Label for="d-secret">{{ t('destinations.secretKey') }}</Label>
              <Input
                id="d-secret"
                v-model="form.secret_key"
                type="password"
                autocomplete="off"
                spellcheck="false"
                class="font-mono text-xs"
                :placeholder="editingId != null ? t('destinations.secretPlaceholderKeep') : ''"
              />
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-x-6 gap-y-2 pt-2">
            <div class="flex items-center gap-2.5">
              <Switch v-model="form.auto_upload" />
              <Label class="text-sm">{{ t('destinations.autoUpload') }}</Label>
            </div>
            <div class="flex items-center gap-2.5">
              <Switch v-model="form.enabled" />
              <Label class="text-sm">{{ t('common.enabled') }}</Label>
            </div>
          </div>

          <div class="flex justify-end gap-2 pt-2">
            <Button variant="ghost" size="sm" @click="closeForm">
              <X />
              {{ t('common.cancel') }}
            </Button>
            <Button
              size="sm"
              :disabled="!formValid() || actions.create.isPending.value || actions.update.isPending.value"
              @click="onSubmit"
            >
              <Loader2
                v-if="actions.create.isPending.value || actions.update.isPending.value"
                class="animate-spin"
              />
              <Plus v-else-if="editingId == null" />
              <Pencil v-else />
              {{ editingId != null ? t('common.save') : t('destinations.create') }}
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
            <th class="px-3 py-2 text-left font-medium hidden sm:table-cell">
              {{ t('destinations.bucket') }}
            </th>
            <th class="px-3 py-2 text-left font-medium hidden md:table-cell">
              {{ t('destinations.endpoint') }}
            </th>
            <th class="px-3 py-2 text-left font-medium">{{ t('destinations.autoUpload') }}</th>
            <th class="w-32 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-if="list.isPending.value && !list.data.value">
            <td colspan="5" class="px-4 py-8 text-center text-muted-foreground">
              {{ t('common.loading') }}
            </td>
          </tr>
          <tr v-else-if="!list.data.value?.length">
            <td colspan="5" class="px-4 py-12 text-center text-muted-foreground">
              <div class="text-base font-medium mb-1">{{ t('destinations.empty') }}</div>
              <div class="text-xs">{{ t('destinations.emptyHint') }}</div>
            </td>
          </tr>
          <tr
            v-for="d in list.data.value ?? []"
            :key="d.id"
            class="border-t border-border hover:bg-accent/30 transition-colors"
          >
            <td class="px-3 py-2">
              <div class="font-medium truncate flex items-center gap-2">
                <span :class="d.enabled ? '' : 'line-through text-muted-foreground'">
                  {{ d.name }}
                </span>
                <span
                  v-if="d.has_secret"
                  class="inline-flex items-center gap-1 text-[11px] text-muted-foreground"
                  :title="t('destinations.secretSet')"
                >
                  <CheckCircle :size="10" />
                  {{ t('destinations.secretSet') }}
                </span>
              </div>
            </td>
            <td class="px-3 py-2 font-mono text-xs text-muted-foreground hidden sm:table-cell">
              {{ d.bucket }}<span v-if="d.prefix">/{{ d.prefix }}</span>
            </td>
            <td class="px-3 py-2 font-mono text-xs text-muted-foreground hidden md:table-cell truncate max-w-[18rem]">
              {{ d.endpoint_url || 'AWS S3' }}
            </td>
            <td class="px-3 py-2">
              <Switch
                :model-value="d.auto_upload"
                @update:model-value="actions.update.mutate({ id: d.id, data: { auto_upload: $event } })"
              />
            </td>
            <td class="px-3 py-2">
              <div class="flex items-center justify-end gap-1">
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors disabled:opacity-50"
                  :disabled="actions.test.isPending.value"
                  :aria-label="t('destinations.test')"
                  :title="t('destinations.test')"
                  @click="actions.test.mutate(d)"
                >
                  <Loader2 v-if="actions.test.isPending.value" class="animate-spin" :size="14" />
                  <RotateCcw v-else :size="14" />
                </button>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :aria-label="t('common.edit')"
                  :title="t('common.edit')"
                  @click="openEdit(d)"
                >
                  <Pencil :size="14" />
                </button>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                  :aria-label="t('common.delete')"
                  :title="t('common.delete')"
                  @click="onDelete(d)"
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
