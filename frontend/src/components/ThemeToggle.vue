<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Moon, Sun } from 'lucide-vue-next'
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()
const { t } = useI18n()
const isDark = computed(() => theme.theme === 'dark')
</script>

<template>
  <button
    type="button"
    class="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    :aria-label="isDark ? t('common.themeLight') : t('common.themeDark')"
    @click="theme.toggle()"
  >
    <Sun v-if="isDark" :size="16" />
    <Moon v-else :size="16" />
  </button>
</template>
