<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { LucideIcon } from 'lucide-vue-next'
import { Construction } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    icon?: LucideIcon
    /** i18n key — preferred. */
    titleKey?: string
    descriptionKey?: string
    ctaKey?: string
    /** Raw fallback strings (used only if `titleKey` not provided). */
    title?: string
    description?: string
    cta?: string
  }>(),
  {
    icon: Construction,
    titleKey: undefined,
    descriptionKey: undefined,
    ctaKey: undefined,
    title: undefined,
    description: undefined,
    cta: undefined,
  },
)

const { t, te } = useI18n()

function tx(key: string | undefined, fallback: string | undefined): string | undefined {
  if (key && te(key)) return t(key)
  return fallback
}

const titleText = () => tx(props.titleKey, props.title) ?? ''
const descText = () => tx(props.descriptionKey, props.description)
const ctaText = () => tx(props.ctaKey, props.cta)
</script>

<template>
  <div class="flex min-h-[60vh] flex-col items-center justify-center text-center px-6">
    <div
      class="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-card border border-border shadow-sm"
    >
      <component
        :is="icon"
        :size="22"
        class="text-brand-500"
      />
    </div>
    <h3 class="text-lg font-semibold tracking-tight mb-2">
      {{ titleText() }}
    </h3>
    <p
      v-if="descText()"
      class="text-sm text-muted-foreground max-w-md leading-relaxed"
    >
      {{ descText() }}
    </p>
    <span
      v-if="ctaText()"
      class="mt-5 inline-flex items-center rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground"
    >
      {{ ctaText() }}
    </span>
  </div>
</template>
