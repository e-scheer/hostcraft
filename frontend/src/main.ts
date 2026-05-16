import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPersistedstate from 'pinia-plugin-persistedstate'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { MotionPlugin } from '@vueuse/motion'

import App from './App.vue'
import { router } from './router'
import { queryClient } from './lib/query'
import { i18n } from './i18n'

import './styles/index.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPersistedstate)

app.use(pinia)
app.use(router)
app.use(i18n)
app.use(VueQueryPlugin, { queryClient })
app.use(MotionPlugin)

app.mount('#app')
