import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { layout: 'blank', title: 'Sign in', public: true },
  },
  {
    path: '/',
    component: () => import('@/components/AppShell.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: 'Dashboard' },
      },
      {
        path: 'console',
        name: 'console',
        component: () => import('@/views/Console.vue'),
        meta: { title: 'Console' },
      },
      {
        path: 'files',
        name: 'files',
        component: () => import('@/views/Files.vue'),
        meta: { title: 'Files' },
      },
      {
        path: 'files/edit',
        name: 'files-edit',
        component: () => import('@/views/FileEditor.vue'),
        meta: { title: 'Edit file' },
      },
      {
        path: 'mods',
        name: 'mods',
        component: () => import('@/views/Mods.vue'),
        meta: { title: 'Mods & plugins' },
      },
      {
        path: 'players',
        name: 'players',
        component: () => import('@/views/Players.vue'),
        meta: { title: 'Players' },
      },
      {
        path: 'backups',
        name: 'backups',
        component: () => import('@/views/Backups.vue'),
        meta: { title: 'Backups' },
      },
      {
        path: 'world',
        name: 'world',
        component: () => import('@/views/World.vue'),
        meta: { title: 'World map' },
      },
      {
        path: 'schedules',
        name: 'schedules',
        component: () => import('@/views/Schedules.vue'),
        meta: { title: 'Schedules' },
      },
      {
        path: 'network',
        name: 'network',
        component: () => import('@/views/Network.vue'),
        meta: { title: 'Network' },
      },
      {
        path: 'runtime',
        name: 'runtime',
        component: () => import('@/views/Runtime.vue'),
        meta: { title: 'Runtime' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/Settings.vue'),
        meta: { title: 'Settings' },
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()

  const isPublic = to.meta?.public === true
  if (!auth.isAuthenticated && !isPublic) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : undefined }
  }
  if (auth.isAuthenticated && to.name === 'login') {
    return { name: 'dashboard' }
  }
})

router.afterEach((to) => {
  if (to.meta?.title) {
    document.title = `${to.meta.title as string} · hostcraft`
  } else {
    document.title = 'hostcraft'
  }
})
