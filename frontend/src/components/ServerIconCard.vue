<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Image as ImageIcon, Loader2, RotateCcw, Upload, Check } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  useServerIcon,
  useApplyPreset,
  useUploadIcon,
  useRemoveIcon,
} from '@/composables/useServerIcon'
import { iconApi } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const dialog = useDialogStore()

const iconQuery = useServerIcon()
const applyPreset = useApplyPreset()
const upload = useUploadIcon()
const remove = useRemoveIcon()

const fileInput = ref<HTMLInputElement | null>(null)

const currentUrl = computed(() => {
  const data = iconQuery.data.value
  if (!data?.current.present) return null
  return iconApi.rawUrl(data.current.etag)
})

const presets = computed(() => iconQuery.data.value?.presets ?? [])
const maxKb = computed(() =>
  Math.round((iconQuery.data.value?.max_upload_bytes ?? 1_048_576) / 1024),
)

function presetLabel(id: string, fallback: string) {
  const k = `icon.presets.${id}`
  return t(k, fallback) || fallback
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  upload.mutate(f, {
    onSettled: () => {
      if (input) input.value = ''
    },
  })
}

async function onReset() {
  const ok = await dialog.confirm({
    title: t('icon.resetTitle'),
    description: t('icon.resetDesc'),
    confirmLabel: t('common.reset'),
    variant: 'destructive',
  })
  if (ok) remove.mutate()
}
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <ImageIcon :size="18" class="text-brand-500" />
        {{ t('icon.title') }}
      </CardTitle>
      <p class="text-xs text-muted-foreground">{{ t('icon.subtitle') }}</p>
    </CardHeader>

    <CardContent class="space-y-5">
      <div
        v-if="iconQuery.isPending.value && !iconQuery.data.value"
        class="flex items-center gap-2 text-sm text-muted-foreground"
      >
        <Loader2 class="animate-spin" :size="14" />
        {{ t('common.loading') }}
      </div>

      <div v-else class="flex flex-col sm:flex-row gap-5">
        <!-- Current preview -->
        <div class="flex flex-col items-center gap-2 shrink-0">
          <div
            class="size-24 rounded-xl border border-border bg-card/40 backdrop-blur overflow-hidden flex items-center justify-center shadow-sm"
            :class="!currentUrl && 'text-muted-foreground'"
          >
            <img
              v-if="currentUrl"
              :src="currentUrl"
              :alt="t('icon.currentAlt')"
              class="size-full object-cover [image-rendering:pixelated]"
            />
            <ImageIcon v-else :size="28" />
          </div>
          <span class="text-[10px] uppercase tracking-wider text-muted-foreground">
            {{ currentUrl ? t('icon.currentLabel') : t('icon.defaultLabel') }}
          </span>
        </div>

        <!-- Actions + presets -->
        <div class="flex-1 min-w-0 space-y-4">
          <div>
            <div class="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">
              {{ t('icon.presetsHeader') }}
            </div>
            <div class="grid grid-cols-4 sm:grid-cols-8 gap-2">
              <button
                v-for="p in presets"
                :key="p.id"
                type="button"
                :disabled="applyPreset.isPending.value"
                class="group relative aspect-square rounded-lg border border-border overflow-hidden transition-all hover:scale-105 hover:border-brand-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:cursor-wait"
                :title="presetLabel(p.id, p.name)"
                @click="applyPreset.mutate(p.id)"
              >
                <img
                  :src="iconApi.presetUrl(p.id)"
                  :alt="p.name"
                  class="size-full object-cover [image-rendering:pixelated]"
                  loading="lazy"
                />
                <span
                  v-if="
                    applyPreset.isPending.value &&
                    applyPreset.variables.value === p.id
                  "
                  class="absolute inset-0 flex items-center justify-center bg-black/50"
                >
                  <Loader2 class="animate-spin text-white" :size="16" />
                </span>
                <span
                  class="absolute inset-x-0 bottom-0 px-1 py-0.5 bg-gradient-to-t from-black/70 to-transparent text-[9px] font-medium text-white truncate text-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  {{ presetLabel(p.id, p.name) }}
                </span>
              </button>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2 pt-2 border-t border-border">
            <input
              ref="fileInput"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              class="hidden"
              @change="onFileChange"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              :disabled="upload.isPending.value"
              @click="fileInput?.click()"
            >
              <Loader2 v-if="upload.isPending.value" class="animate-spin" />
              <Upload v-else :size="14" />
              {{ upload.isPending.value ? t('icon.uploading') : t('icon.upload') }}
            </Button>

            <Button
              v-if="iconQuery.data.value?.current.present"
              type="button"
              variant="ghost"
              size="sm"
              :disabled="remove.isPending.value"
              @click="onReset"
            >
              <Loader2 v-if="remove.isPending.value" class="animate-spin" />
              <RotateCcw v-else :size="14" />
              {{ t('icon.reset') }}
            </Button>

            <span
              v-if="upload.isSuccess.value && !upload.isPending.value"
              class="inline-flex items-center gap-1 text-xs text-emerald-500"
            >
              <Check :size="12" />
              {{ t('icon.savedHint') }}
            </span>

            <span class="ml-auto text-[11px] text-muted-foreground">
              {{ t('icon.uploadHint', { size: 64, max: maxKb }) }}
            </span>
          </div>

          <p class="text-[11px] text-muted-foreground italic">
            {{ t('icon.restartHint') }}
          </p>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
