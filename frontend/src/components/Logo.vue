<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: number
    showWordmark?: boolean
  }>(),
  { size: 28, showWordmark: true },
)
</script>

<template>
  <div class="flex items-center gap-2.5">
    <svg
      :width="size"
      :height="size"
      viewBox="0 0 64 64"
      fill="none"
      class="shrink-0 drop-shadow-[0_2px_8px_rgba(16,185,129,0.18)]"
    >
      <path d="M32 6 L58 19 L32 32 L6 19 Z" fill="oklch(0.78 0.16 155)" />
      <path d="M6 19 L32 32 L32 58 L6 45 Z" fill="oklch(0.55 0.16 155)" />
      <path d="M58 19 L32 32 L32 58 L58 45 Z" fill="oklch(0.42 0.13 155)" />
      <path d="M32 6 L58 19 L32 32 Z" fill="white" fill-opacity="0.06" />
    </svg>
    <span
      v-if="showWordmark"
      class="text-[15px] font-semibold tracking-tight leading-none select-none"
    >
      <span class="text-gradient-brand">h</span><span class="text-foreground">ostcraft</span>
    </span>
  </div>
</template>
