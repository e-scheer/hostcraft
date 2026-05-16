import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

type Theme = 'light' | 'dark' | 'system'

function applyTheme(theme: Theme) {
  const dark =
    theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
}

export const useThemeStore = defineStore('theme', () => {
  const stored = (localStorage.getItem('hostcraft.theme') as Theme | null) ?? 'dark'
  const theme = ref<Theme>(stored)

  applyTheme(theme.value)

  watch(theme, (value) => {
    localStorage.setItem('hostcraft.theme', value)
    applyTheme(value)
  })

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  return { theme, toggle }
})
