<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Activity, CheckCircle2, XCircle } from 'lucide-vue-next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useRecentActivity } from '@/composables/useAudit'
import { formatRelativeTime } from '@/composables/useFiles'

const { t, te } = useI18n()
const activity = useRecentActivity(8)

function unixOf(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000)
}

/**
 * Pretty-print a dotted action like "server.start" → "Server / Start".
 * Specific verbs get a translated label; the rest falls back to title-case.
 * We probe with ``te()`` first so missing keys don't spam the console — the
 * audit log emits arbitrary dotted actions and we can't enumerate them all.
 */
function actionLabel(action: string): string {
  const k = `activity.actions.${action}`
  if (te(k)) return t(k)
  return action
    .split('.')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(' / ')
}
</script>

<template>
  <Card>
    <CardHeader class="flex flex-row items-center justify-between gap-2 space-y-0">
      <div class="space-y-1">
        <CardTitle class="flex items-center gap-2">
          <Activity
            :size="16"
            class="text-brand-500"
          />
          {{ t('activity.title') }}
        </CardTitle>
        <CardDescription>{{ t('activity.subtitle') }}</CardDescription>
      </div>
    </CardHeader>
    <CardContent class="px-0 pb-2">
      <div
        v-if="activity.isPending.value && !activity.data.value"
        class="px-6 py-3 text-xs text-muted-foreground"
      >
        {{ t('common.loading') }}
      </div>
      <div
        v-else-if="!activity.data.value?.length"
        class="px-6 py-6 text-center text-xs text-muted-foreground"
      >
        {{ t('activity.empty') }}
      </div>
      <ul
        v-else
        class="divide-y divide-border"
      >
        <li
          v-for="entry in activity.data.value ?? []"
          :key="entry.id"
          class="flex items-center gap-3 px-6 py-2.5 hover:bg-accent/30 transition-colors"
        >
          <CheckCircle2
            v-if="entry.status === 'success'"
            :size="14"
            class="text-brand-500 shrink-0"
          />
          <XCircle
            v-else
            :size="14"
            class="text-destructive shrink-0"
          />

          <div class="min-w-0 flex-1">
            <div class="text-sm truncate">
              <span class="font-medium">{{ actionLabel(entry.action) }}</span>
              <span
                v-if="entry.target && !entry.target.startsWith('/api/')"
                class="text-muted-foreground ml-1.5 font-mono text-xs"
              >
                {{ entry.target }}
              </span>
            </div>
            <div class="text-[11px] text-muted-foreground tabular-nums">
              {{ entry.user ?? '—' }}
              <span class="opacity-60 mx-1">·</span>
              {{ formatRelativeTime(unixOf(entry.created_at)) }}
              <span
                v-if="entry.duration_ms != null"
                class="opacity-60 ml-1"
              >
                · {{ entry.duration_ms }} ms
              </span>
            </div>
          </div>

          <span class="text-[10px] font-mono text-muted-foreground tabular-nums shrink-0">
            {{ entry.status_code }}
          </span>
        </li>
      </ul>
    </CardContent>
  </Card>
</template>
