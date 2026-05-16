<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  LayoutDashboard,
  Terminal,
  FolderTree,
  Package,
  Users,
  Archive,
  Map,
  Cpu,
  CalendarClock,
  Cable,
  Settings,
  Power,
  Menu as MenuIcon,
  LogOut,
  type LucideIcon,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import Logo from './Logo.vue'
import ThemeToggle from './ThemeToggle.vue'
import LanguageToggle from './LanguageToggle.vue'
import { useAuthStore } from '@/stores/auth'
import { useServerActions, useServerView } from '@/composables/useServer'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

interface NavItem {
  to: string
  labelKey: string
  icon: LucideIcon
}

const navItems: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard },
  { to: '/console', labelKey: 'nav.console', icon: Terminal },
  { to: '/files', labelKey: 'nav.files', icon: FolderTree },
  { to: '/mods', labelKey: 'nav.mods', icon: Package },
  { to: '/players', labelKey: 'nav.players', icon: Users },
  { to: '/backups', labelKey: 'nav.backups', icon: Archive },
  { to: '/world', labelKey: 'nav.world', icon: Map },
  { to: '/schedules', labelKey: 'nav.schedules', icon: CalendarClock },
  { to: '/network', labelKey: 'nav.network', icon: Cable },
  { to: '/runtime', labelKey: 'nav.runtime', icon: Cpu },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings },
]

const sidebarOpen = ref(false)

const currentTitle = computed(() => {
  const item = navItems.find((n) =>
    n.to === '/' ? route.path === '/' : route.path.startsWith(n.to),
  )
  return item ? t(item.labelKey) : 'hostcraft'
})

function onLogout() {
  auth.logout()
  toast.success(t('auth.signedOut'))
  router.push({ name: 'login' })
}

const userInitials = computed(() => {
  const name = auth.user?.username ?? '?'
  return name.slice(0, 2).toUpperCase()
})

const { label: statusLabel, dotClass: statusDotClass, isBusy, isRunning } = useServerView()
const { start: startMutation, stop: stopMutation } = useServerActions()

function onTogglePower() {
  if (isBusy.value) return
  if (isRunning.value) stopMutation.mutate()
  else startMutation.mutate()
}
</script>

<template>
  <div class="min-h-screen flex bg-background text-foreground">
    <aside
      class="fixed lg:static inset-y-0 left-0 z-40 w-64 shrink-0 border-r border-border bg-card/40 backdrop-blur-md flex flex-col transition-transform"
      :class="sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'"
    >
      <div class="px-5 py-5 border-b border-border">
        <RouterLink to="/" class="block">
          <Logo />
        </RouterLink>
      </div>

      <nav class="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          v-slot="{ isActive, isExactActive }"
          :to="item.to"
          custom
        >
          <a
            :href="item.to"
            class="group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors"
            :class="[
              (item.to === '/' ? isExactActive : isActive)
                ? 'bg-accent text-foreground font-medium'
                : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
            ]"
            @click.prevent="$router.push(item.to); sidebarOpen = false"
          >
            <component
              :is="item.icon"
              :size="16"
              class="transition-colors"
              :class="(item.to === '/' ? isExactActive : isActive) ? 'text-brand-500' : ''"
            />
            <span>{{ t(item.labelKey) }}</span>
          </a>
        </RouterLink>
      </nav>

      <div class="px-4 py-4 border-t border-border space-y-3">
        <div class="flex items-center gap-2.5 text-xs">
          <span class="size-2 rounded-full" :class="statusDotClass" />
          <span class="text-muted-foreground">{{ t('server.label') }}</span>
          <span class="ml-auto font-medium">{{ statusLabel }}</span>
        </div>
        <button
          type="button"
          class="w-full inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium h-9 px-3 transition-colors disabled:opacity-60 disabled:cursor-wait"
          :class="
            isRunning
              ? 'bg-card border border-border text-foreground hover:bg-accent'
              : 'bg-primary text-primary-foreground hover:bg-primary/90'
          "
          :disabled="isBusy"
          @click="onTogglePower"
        >
          <Power :size="14" />
          {{ isBusy
              ? t('server.states.working')
              : isRunning ? t('server.actions.stopServer') : t('server.actions.startServer')
          }}
        </button>

        <div class="flex items-center gap-2.5 pt-3 border-t border-border">
          <div
            class="flex h-8 w-8 items-center justify-center rounded-full bg-brand-700/20 text-brand-300 text-xs font-semibold"
          >
            {{ userInitials }}
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium truncate leading-tight">
              {{ auth.user?.username ?? '—' }}
            </div>
            <div class="text-[10px] text-muted-foreground uppercase tracking-wider">
              {{ auth.user?.is_staff ? t('auth.roleAdmin') : t('auth.roleUser') }}
            </div>
          </div>
          <button
            type="button"
            class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            :aria-label="t('auth.signOut')"
            :title="t('auth.signOut')"
            @click="onLogout"
          >
            <LogOut :size="14" />
          </button>
        </div>
      </div>
    </aside>

    <button
      v-if="sidebarOpen"
      class="lg:hidden fixed inset-0 z-30 bg-black/50 backdrop-blur-sm"
      :aria-label="t('common.close')"
      @click="sidebarOpen = false"
    />

    <div class="flex-1 flex flex-col min-w-0">
      <header
        class="sticky top-0 z-20 h-14 border-b border-border bg-background/70 backdrop-blur-md flex items-center px-4 sm:px-6"
      >
        <button
          type="button"
          class="lg:hidden mr-2 inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="menu"
          @click="sidebarOpen = true"
        >
          <MenuIcon :size="18" />
        </button>
        <h1 class="text-sm font-semibold tracking-tight">
          {{ currentTitle }}
        </h1>
        <div class="ml-auto flex items-center gap-2">
          <LanguageToggle />
          <ThemeToggle />
        </div>
      </header>

      <main class="flex-1 px-4 sm:px-6 py-6 max-w-[1600px] w-full mx-auto">
        <RouterView v-slot="{ Component }">
          <Transition name="view-fade" mode="out-in">
            <KeepAlive :max="8">
              <component :is="Component" />
            </KeepAlive>
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>

<!-- view-fade transition lives in src/styles/animations.css -->
