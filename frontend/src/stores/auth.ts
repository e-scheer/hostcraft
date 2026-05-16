import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { HTTPError } from 'ky'
import { authApi, type CurrentUser, type LoginPayload } from '@/lib/api'

const TOKEN_KEY = 'hostcraft.token'
const REFRESH_KEY = 'hostcraft.refresh'

export const useAuthStore = defineStore(
  'auth',
  () => {
    const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
    const refreshToken = ref<string | null>(localStorage.getItem(REFRESH_KEY))
    const user = ref<CurrentUser | null>(null)
    const initialized = ref(false)

    const isAuthenticated = computed(() => token.value !== null && user.value !== null)

    function persist(access: string | null, refresh: string | null) {
      token.value = access
      refreshToken.value = refresh
      if (access) localStorage.setItem(TOKEN_KEY, access)
      else localStorage.removeItem(TOKEN_KEY)
      if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
      else localStorage.removeItem(REFRESH_KEY)
    }

    /** Try to load the current user. Called once at app boot. */
    async function bootstrap() {
      if (initialized.value) return
      initialized.value = true
      if (!token.value) return
      try {
        user.value = await authApi.me()
      } catch (err) {
        if (err instanceof HTTPError && err.response.status === 401) {
          persist(null, null)
          user.value = null
        } else {
          // Network error — keep tokens; UI will retry on next call.
          console.warn('Auth bootstrap failed:', err)
        }
      }
    }

    async function login(payload: LoginPayload) {
      const tokens = await authApi.login(payload)
      persist(tokens.access, tokens.refresh)
      user.value = await authApi.me()
    }

    function logout() {
      persist(null, null)
      user.value = null
    }

    return { token, refreshToken, user, initialized, isAuthenticated, bootstrap, login, logout }
  },
)
