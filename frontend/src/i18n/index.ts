import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import fr from '@/locales/fr.json'

export const SUPPORTED_LOCALES = ['en', 'fr'] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

const STORAGE_KEY = 'hostcraft.locale'

function detectLocale(): SupportedLocale {
  const stored = localStorage.getItem(STORAGE_KEY) as SupportedLocale | null
  if (stored && SUPPORTED_LOCALES.includes(stored)) return stored

  const navigatorLocale = navigator.language.slice(0, 2).toLowerCase() as SupportedLocale
  if (SUPPORTED_LOCALES.includes(navigatorLocale)) return navigatorLocale

  return 'en'
}

export const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'en',
  missingWarn: import.meta.env.DEV,
  fallbackWarn: import.meta.env.DEV,
  messages: { en, fr },
})

export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  localStorage.setItem(STORAGE_KEY, locale)
  document.documentElement.lang = locale
}

export function getLocale(): SupportedLocale {
  return i18n.global.locale.value as SupportedLocale
}

// Apply on initial load.
document.documentElement.lang = i18n.global.locale.value
