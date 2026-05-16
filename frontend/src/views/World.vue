<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Map as MapIcon,
  RotateCcw,
  Sparkles,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useDialogStore } from '@/stores/dialog'
import { useWorldmap, useInstallWorldmap } from '@/composables/useWorldmap'
import { useModTarget } from '@/composables/useMods'

const { t } = useI18n()
const dialog = useDialogStore()

const wm = useWorldmap()
const install = useInstallWorldmap()
const target = useModTarget()

const iframeReloadKey = ref(0)

// BlueMap's HTTP server binds to 0.0.0.0:8100 inside the MC container and
// the panel adds an Allocation that publishes it on the host's :8100.
// We point the iframe at whatever host the user is using to reach the
// panel — works for localhost AND remote setups behind a reverse proxy.
const mapUrl = computed(() => {
  const port = wm.data.value?.web_port ?? 8100
  const host =
    typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  return `http://${host}:${port}/`
})

async function onInstall() {
  if (install.isPending.value) return
  const ok = await dialog.confirm({
    title: t('world.setup.confirmTitle'),
    description: t('world.setup.confirmBody', {
      loader: target.data.value?.loader_label ?? '?',
      mc: target.data.value?.mc_version ?? '?',
    }),
    confirmLabel: t('world.setup.confirmCta'),
  })
  if (!ok) return
  install.mutate()
}

function reloadIframe() {
  iframeReloadKey.value++
}
</script>

<template>
  <div class="space-y-6">
    <header class="space-y-1">
      <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <MapIcon
          :size="22"
          class="text-brand-500"
        />
        {{ t('world.title') }}
      </h2>
      <p class="text-sm text-muted-foreground">
        {{ t('world.subtitle') }}
      </p>
    </header>

    <!-- Loading state — first paint, before status is known -->
    <div
      v-if="wm.isPending.value && !wm.data.value"
      class="flex items-center gap-2 text-sm text-muted-foreground"
    >
      <Loader2
        class="animate-spin"
        :size="14"
      />
      {{ t('common.loading') }}
    </div>

    <!-- ============================================================== -->
    <!-- Unsupported engine (Vanilla, unknown)                            -->
    <!-- ============================================================== -->
    <Card
      v-else-if="wm.data.value?.state === 'unsupported'"
      class="border-amber-500/30"
    >
      <CardContent class="p-5 flex items-start gap-3">
        <AlertTriangle
          :size="20"
          class="text-amber-500 shrink-0 mt-0.5"
        />
        <div class="space-y-1">
          <div class="font-medium">
            {{ t('world.unsupported.title') }}
          </div>
          <p class="text-sm text-muted-foreground leading-relaxed">
            {{ t('world.unsupported.body', { type: wm.data.value.target_loader || '?' }) }}
          </p>
        </div>
      </CardContent>
    </Card>

    <!-- ============================================================== -->
    <!-- Setup card — BlueMap not yet on disk                             -->
    <!-- ============================================================== -->
    <Card v-else-if="wm.data.value?.state === 'not_installed'">
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <Sparkles
            :size="18"
            class="text-brand-500"
          />
          {{ t('world.setup.title') }}
        </CardTitle>
        <p class="text-xs text-muted-foreground mt-1">
          {{ t('world.setup.subtitle') }}
        </p>
      </CardHeader>
      <CardContent class="space-y-5">
        <!-- What you'll get -->
        <ul class="space-y-2 text-sm">
          <li
            v-for="line in (['feature1', 'feature2', 'feature3'] as const)"
            :key="line"
            class="flex items-start gap-2"
          >
            <CheckCircle2
              :size="14"
              class="text-brand-500 shrink-0 mt-0.5"
            />
            <span>{{ t(`world.setup.${line}`) }}</span>
          </li>
        </ul>

        <!-- Target info -->
        <div class="rounded-lg border border-border bg-card/40 backdrop-blur p-3 text-xs space-y-1">
          <div class="text-muted-foreground uppercase tracking-wider text-[10px]">
            {{ t('world.setup.willInstallOn') }}
          </div>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-medium">{{ target.data.value?.loader_label ?? '—' }}</span>
            <span class="text-muted-foreground">·</span>
            <span class="font-mono">{{ target.data.value?.mc_version ?? '—' }}</span>
            <span
              v-if="target.data.value?.mc_version_alias"
              class="text-muted-foreground/70"
            >
              ({{ target.data.value.mc_version_alias }})
            </span>
            <span
              class="ml-auto px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-brand-500/10 text-brand-500"
            >
              port {{ wm.data.value.web_port }}
            </span>
          </div>
        </div>

        <Button
          type="button"
          size="lg"
          :disabled="install.isPending.value || !target.data.value"
          @click="onInstall"
        >
          <Loader2
            v-if="install.isPending.value"
            class="animate-spin"
            :size="16"
          />
          <Sparkles
            v-else
            :size="16"
          />
          {{
            install.isPending.value
              ? t('world.setup.installing')
              : t('world.setup.cta')
          }}
        </Button>

        <p class="text-[11px] text-muted-foreground italic leading-snug">
          {{ t('world.setup.note') }}
        </p>
      </CardContent>
    </Card>

    <!-- ============================================================== -->
    <!-- Installed — embed the BlueMap webserver                          -->
    <!-- ============================================================== -->
    <template v-else-if="wm.data.value?.state === 'installed'">
      <div class="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
        <span class="inline-flex items-center gap-1.5 text-emerald-500 font-medium">
          <CheckCircle2 :size="12" />
          {{ t('world.installed.ready') }}
        </span>
        <span class="text-muted-foreground/40">·</span>
        <span class="font-mono">{{ wm.data.value.filename }}</span>
        <span class="ml-auto inline-flex items-center gap-3">
          <button
            type="button"
            class="inline-flex items-center gap-1 hover:text-foreground"
            @click="reloadIframe"
          >
            <RotateCcw :size="11" />
            {{ t('world.installed.reload') }}
          </button>
          <a
            :href="mapUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 text-brand-500 hover:underline"
          >
            <ExternalLink :size="11" />
            {{ t('world.installed.openInTab') }}
          </a>
        </span>
      </div>

      <Card class="overflow-hidden">
        <iframe
          :key="iframeReloadKey"
          :src="mapUrl"
          class="block w-full h-[72vh] border-0 bg-background"
          :title="t('world.installed.iframeTitle')"
          referrerpolicy="no-referrer"
        />
      </Card>

      <p class="text-[11px] text-muted-foreground italic">
        {{ t('world.installed.tilesNote') }}
      </p>
    </template>
  </div>
</template>
