<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Loader2, Save, Settings as SettingsIcon } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useProperties, useSaveProperties } from '@/composables/useProperties'
import type { PropertySpec } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'
import ServerIconCard from '@/components/ServerIconCard.vue'

const { t, te } = useI18n()
const dialog = useDialogStore()
const propsQuery = useProperties()
const save = useSaveProperties()

// Local working copy of values. Reset whenever the server-side data changes
// AND we're not currently dirty (avoids stomping on the user's edits).
const local = ref<Record<string, string | number | boolean>>({})
const initial = ref<Record<string, string | number | boolean>>({})

watch(
  () => propsQuery.data.value,
  (data) => {
    if (!data) return
    if (Object.keys(local.value).length === 0 || !isDirty.value) {
      local.value = { ...data.values }
      initial.value = { ...data.values }
    }
  },
  { immediate: true },
)

const isDirty = computed(() => {
  const a = local.value
  const b = initial.value
  return Object.keys(a).some((k) => a[k] !== b[k]) || Object.keys(b).some((k) => !(k in a))
})

function fieldLabel(key: string) {
  const i18nKey = `settings.fields.${key}.label`
  return te(i18nKey) ? t(i18nKey) : key
}

function fieldHelp(key: string) {
  const i18nKey = `settings.fields.${key}.help`
  return te(i18nKey) ? t(i18nKey) : ''
}

function sectionLabel(section: string) {
  const k = `settings.sections.${section}`
  return te(k) ? t(k) : section
}

function fieldsBySection(section: string) {
  const schema = propsQuery.data.value?.schema ?? {}
  return Object.entries(schema)
    .filter(([, spec]) => spec.section === section)
    .map(([key, spec]) => ({ key, spec: spec as PropertySpec }))
}

function onSubmit() {
  if (!isDirty.value || save.isPending.value) return
  save.mutate({ ...local.value })
}

function onReset() {
  local.value = { ...initial.value }
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
    <header class="flex flex-wrap items-end justify-between gap-4">
      <div class="space-y-1">
        <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <SettingsIcon :size="22" class="text-brand-500" />
          {{ t('settings.title') }}
        </h2>
        <p class="text-sm text-muted-foreground">{{ t('settings.subtitle') }}</p>
      </div>
    </header>

    <ServerIconCard />

    <!-- Loading -->
    <div
      v-if="propsQuery.isPending.value && !propsQuery.data.value"
      class="flex items-center gap-2 text-muted-foreground text-sm"
    >
      <Loader2 class="animate-spin" :size="14" />
      {{ t('settings.loading') }}
    </div>

    <!-- Error -->
    <div
      v-else-if="propsQuery.isError.value"
      class="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive"
    >
      {{ propsQuery.error.value?.message ?? t('settings.loadFailed') }}
    </div>

    <!-- Form -->
    <form
      v-else-if="propsQuery.data.value"
      class="space-y-4"
      @submit.prevent="onSubmit"
    >
      <Card
        v-for="section in propsQuery.data.value.sections"
        :key="section"
      >
        <CardHeader>
          <CardTitle>{{ sectionLabel(section) }}</CardTitle>
        </CardHeader>
        <CardContent class="space-y-5">
          <div
            v-for="{ key, spec } in fieldsBySection(section)"
            :key="key"
            class="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-2 sm:gap-6 sm:items-start"
          >
            <div class="min-w-0">
              <Label :for="`f-${key}`" class="block">
                {{ fieldLabel(key) }}
              </Label>
              <p class="text-[11px] font-mono text-muted-foreground/70 mt-0.5 truncate">
                {{ key }}
              </p>
              <p
                v-if="fieldHelp(key)"
                class="text-xs text-muted-foreground mt-1 leading-snug"
              >
                {{ fieldHelp(key) }}
              </p>
            </div>

            <div class="flex items-center min-w-0">
              <!-- boolean -->
              <template v-if="spec.type === 'boolean'">
                <Switch
                  :id="`f-${key}`"
                  :model-value="Boolean(local[key])"
                  @update:model-value="local[key] = $event"
                />
              </template>

              <!-- enum -->
              <select
                v-else-if="spec.type === 'enum'"
                :id="`f-${key}`"
                :value="local[key]"
                class="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
                @change="local[key] = ($event.target as HTMLSelectElement).value"
              >
                <option
                  v-for="opt in spec.options ?? []"
                  :key="opt"
                  :value="opt"
                >
                  {{ opt }}
                </option>
              </select>

              <!-- integer -->
              <Input
                v-else-if="spec.type === 'integer'"
                :id="`f-${key}`"
                type="number"
                :model-value="local[key] as number"
                :min="spec.min"
                :max="spec.max"
                class="max-w-[12rem]"
                @update:model-value="local[key] = Number($event)"
              />

              <!-- string (default) -->
              <Input
                v-else
                :id="`f-${key}`"
                :model-value="local[key] as string"
                :maxlength="spec.max_length"
                @update:model-value="local[key] = $event"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <p class="text-xs text-muted-foreground italic">
        {{ t('settings.restartHint') }}
      </p>

      <!-- Sticky save bar -->
      <Transition name="view-fade">
        <div
          v-if="isDirty"
          class="fixed bottom-4 inset-x-4 sm:left-auto sm:right-6 sm:bottom-6 z-30 flex items-center gap-3 rounded-xl border border-border bg-card/90 backdrop-blur-md shadow-2xl px-4 py-3 max-w-fit"
        >
          <span class="inline-flex items-center gap-1.5 text-sm">
            <span class="size-1.5 rounded-full bg-amber-400 animate-pulse" />
            {{ t('settings.unsaved') }}
          </span>
          <Button type="button" variant="ghost" size="sm" :disabled="save.isPending.value" @click="onReset">
            {{ t('common.cancel') }}
          </Button>
          <Button type="submit" :disabled="save.isPending.value">
            <Loader2 v-if="save.isPending.value" class="animate-spin" />
            <Save v-else />
            {{ save.isPending.value ? t('settings.saving') : t('settings.save') }}
          </Button>
        </div>
      </Transition>
    </form>
  </div>
</template>
