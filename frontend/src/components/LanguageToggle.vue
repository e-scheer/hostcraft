<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuTrigger,
} from 'reka-ui'
import { Check, ChevronDown, Languages } from 'lucide-vue-next'
import { setLocale, SUPPORTED_LOCALES, type SupportedLocale } from '@/i18n'

const { locale, t } = useI18n()

const LANG_NAMES: Record<SupportedLocale, string> = {
  en: 'English',
  fr: 'Français',
}
</script>

<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger
      class="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
      :aria-label="t('common.language')"
    >
      <Languages :size="14" />
      <span class="hidden sm:inline text-foreground">
        {{ LANG_NAMES[locale as SupportedLocale] }}
      </span>
      <ChevronDown :size="12" class="opacity-60" />
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        :side-offset="6"
        align="end"
        class="z-50 min-w-[10rem] rounded-md border border-border bg-popover text-popover-foreground p-1 shadow-xl focus-visible:outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-1"
      >
        <DropdownMenuItem
          v-for="l in SUPPORTED_LOCALES"
          :key="l"
          class="relative flex items-center gap-2 rounded-sm px-2.5 py-1.5 text-sm cursor-pointer select-none outline-none data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground transition-colors"
          @select="setLocale(l)"
        >
          <Check
            :size="14"
            class="text-brand-500 transition-opacity"
            :class="locale === l ? 'opacity-100' : 'opacity-0'"
          />
          <span>{{ LANG_NAMES[l] }}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
