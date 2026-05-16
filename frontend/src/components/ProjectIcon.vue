<script setup lang="ts">
import { ref, watch } from 'vue'
import { Package, type LucideIcon } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    url?: string | null
    alt?: string
    size?: 'sm' | 'md' | 'lg'
    fallbackIcon?: LucideIcon
  }>(),
  {
    url: '',
    alt: '',
    size: 'md',
    fallbackIcon: () => Package,
  },
)

const failed = ref(false)
// Reset on URL change so a fresh src gets a fresh chance.
watch(() => props.url, () => { failed.value = false })

const sizeClass = {
  sm: { box: 'size-10 rounded-md', icon: 16 },
  md: { box: 'size-12 rounded-lg', icon: 20 },
  lg: { box: 'size-16 rounded-xl', icon: 24 },
}[props.size]
</script>

<template>
  <div
    :class="[
      sizeClass.box,
      'overflow-hidden shrink-0 bg-muted/60 flex items-center justify-center',
    ]"
  >
    <img
      v-if="url && !failed"
      :src="url"
      :alt="alt"
      class="size-full object-cover"
      loading="lazy"
      referrerpolicy="no-referrer"
      @error="failed = true"
    >
    <component
      :is="fallbackIcon"
      v-else
      :size="sizeClass.icon"
      class="text-muted-foreground/60"
    />
  </div>
</template>
