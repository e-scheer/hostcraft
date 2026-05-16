<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Loader2 } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Logo from '@/components/Logo.vue'
import LanguageToggle from '@/components/LanguageToggle.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { useAuthStore } from '@/stores/auth'
import { extractErrorMessage } from '@/lib/api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()

const username = ref('')
const password = ref('')
const submitting = ref(false)

async function onSubmit() {
  if (!username.value || !password.value) return
  submitting.value = true
  try {
    await auth.login({ username: username.value, password: password.value })
    toast.success(t('auth.welcomeToast'), {
      description: t('auth.welcomeDesc', { name: auth.user?.username ?? '' }),
    })
    const redirect = (route.query.redirect as string | undefined) ?? '/'
    router.push(redirect)
  } catch (err) {
    const message = await extractErrorMessage(err)
    toast.error(t('auth.signInFailed'), { description: message })
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background p-6">
    <div
      class="absolute inset-0 -z-10 pointer-events-none opacity-60"
      style="background:
        radial-gradient(ellipse 80% 50% at 50% -10%, oklch(0.55 0.16 155 / 0.15), transparent 70%),
        radial-gradient(ellipse 60% 50% at 50% 110%, oklch(0.42 0.13 155 / 0.12), transparent 70%);"
    />

    <div class="absolute top-4 right-4 flex gap-2">
      <LanguageToggle />
      <ThemeToggle />
    </div>

    <Card class="w-full max-w-sm border-border/80 bg-card/80 backdrop-blur-md shadow-xl">
      <CardContent class="p-8">
        <div class="flex flex-col items-center gap-2 mb-8">
          <Logo :size="40" :show-wordmark="false" />
          <h1 class="text-xl font-semibold tracking-tight mt-2">{{ t('auth.title') }}</h1>
          <p class="text-sm text-muted-foreground">{{ t('auth.subtitle') }}</p>
        </div>

        <form class="space-y-4" @submit.prevent="onSubmit">
          <div class="space-y-1.5">
            <Label for="username">{{ t('auth.username') }}</Label>
            <Input
              id="username"
              v-model="username"
              autocomplete="username"
              :disabled="submitting"
            />
          </div>
          <div class="space-y-1.5">
            <Label for="password">{{ t('auth.password') }}</Label>
            <Input
              id="password"
              v-model="password"
              type="password"
              autocomplete="current-password"
              :disabled="submitting"
            />
          </div>
          <Button type="submit" class="w-full" :disabled="submitting || !username || !password">
            <Loader2 v-if="submitting" class="animate-spin" />
            <span>{{ submitting ? t('auth.signingIn') : t('auth.signIn') }}</span>
          </Button>
        </form>
      </CardContent>
    </Card>
  </div>
</template>
