<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loader2, ShieldCheck, Trash2, UserPlus, Users as UsersIcon } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  useOps,
  useOpsActions,
  useWhitelist,
  useWhitelistActions,
} from '@/composables/usePlayers'
import type { OpEntry, WhitelistEntry } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const dialog = useDialogStore()

type Tab = 'whitelist' | 'ops'
const tab = ref<Tab>('whitelist')

// --- whitelist -------------------------------------------------------------
const whitelist = useWhitelist()
const whitelistActions = useWhitelistActions()
const whitelistName = ref('')

function onWhitelistAdd() {
  if (!whitelistName.value.trim()) return
  whitelistActions.add.mutate(whitelistName.value.trim(), {
    onSuccess: () => {
      whitelistName.value = ''
    },
  })
}

async function onWhitelistRemove(entry: WhitelistEntry) {
  const ok = await dialog.confirm({
    title: t('players.confirmRemoveWhitelist', { name: entry.name }),
    confirmLabel: t('players.remove'),
    variant: 'destructive',
  })
  if (!ok) return
  whitelistActions.remove.mutate(entry)
}

// --- ops -------------------------------------------------------------------
const ops = useOps()
const opsActions = useOpsActions()
const opName = ref('')
const opLevel = ref(4)
const opBypass = ref(false)

function onOpAdd() {
  if (!opName.value.trim()) return
  opsActions.add.mutate(
    { name: opName.value.trim(), level: opLevel.value, bypassesPlayerLimit: opBypass.value },
    {
      onSuccess: () => {
        opName.value = ''
      },
    },
  )
}

function onOpLevelChange(entry: OpEntry, level: number) {
  opsActions.update.mutate({ uuid: entry.uuid, level })
}

function onOpBypassChange(entry: OpEntry, bypass: boolean) {
  opsActions.update.mutate({ uuid: entry.uuid, bypassesPlayerLimit: bypass })
}

async function onOpRemove(entry: OpEntry) {
  const ok = await dialog.confirm({
    title: t('players.confirmRemoveOp', { name: entry.name }),
    confirmLabel: t('players.remove'),
    variant: 'destructive',
  })
  if (!ok) return
  opsActions.remove.mutate(entry)
}
</script>

<template>
  <div class="space-y-6">
    <header class="space-y-1">
      <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <UsersIcon
          :size="22"
          class="text-brand-500"
        />
        {{ t('players.title') }}
      </h2>
      <p class="text-sm text-muted-foreground">
        {{ t('players.subtitle') }}
      </p>
    </header>

    <!-- Tabs -->
    <div
      role="tablist"
      class="inline-flex rounded-lg border border-border bg-card p-1 gap-1"
    >
      <button
        v-for="key in (['whitelist', 'ops'] as const)"
        :key="key"
        role="tab"
        type="button"
        class="px-4 py-1.5 text-sm font-medium rounded-md transition-colors"
        :class="
          tab === key
            ? 'bg-accent text-foreground'
            : 'text-muted-foreground hover:text-foreground'
        "
        @click="tab = key"
      >
        {{ t(`players.tabs.${key}`) }}
      </button>
    </div>

    <!-- WHITELIST -->
    <section
      v-if="tab === 'whitelist'"
      class="space-y-4"
    >
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <ShieldCheck
              :size="18"
              class="text-brand-500"
            />
            {{ t('players.whitelist.title') }}
          </CardTitle>
          <p class="text-xs text-muted-foreground mt-1">
            {{ t('players.whitelist.subtitle') }}
          </p>
        </CardHeader>
        <CardContent class="space-y-4">
          <form
            class="flex flex-col sm:flex-row gap-2"
            @submit.prevent="onWhitelistAdd"
          >
            <div class="flex-1 space-y-1.5">
              <Label for="wl-name">{{ t('players.whitelist.addLabel') }}</Label>
              <Input
                id="wl-name"
                v-model="whitelistName"
                :placeholder="t('players.whitelist.addPlaceholder')"
                autocomplete="off"
              />
            </div>
            <Button
              type="submit"
              class="sm:self-end"
              :disabled="!whitelistName.trim() || whitelistActions.add.isPending.value"
            >
              <Loader2
                v-if="whitelistActions.add.isPending.value"
                class="animate-spin"
              />
              <UserPlus v-else />
              {{ t('players.whitelist.add') }}
            </Button>
          </form>

          <div class="rounded-lg border border-border overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th class="px-3 py-2 text-left font-medium">
                    {{ t('players.headers.player') }}
                  </th>
                  <th class="px-3 py-2 text-left font-medium hidden md:table-cell">
                    {{ t('players.headers.uuid') }}
                  </th>
                  <th class="w-16 px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                <tr v-if="whitelist.isPending.value && !whitelist.data.value">
                  <td
                    colspan="3"
                    class="px-4 py-8 text-center text-muted-foreground"
                  >
                    {{ t('common.loading') }}
                  </td>
                </tr>
                <tr v-else-if="!whitelist.data.value?.length">
                  <td
                    colspan="3"
                    class="px-4 py-8 text-center text-muted-foreground"
                  >
                    {{ t('players.whitelist.empty') }}
                  </td>
                </tr>
                <tr
                  v-for="entry in whitelist.data.value ?? []"
                  :key="entry.uuid"
                  class="border-t border-border hover:bg-accent/30 transition-colors"
                >
                  <td class="px-3 py-2">
                    <div class="flex items-center gap-2.5">
                      <img
                        :src="`https://mc-heads.net/avatar/${entry.uuid}/24`"
                        :alt="entry.name"
                        class="size-6 rounded-md"
                        loading="lazy"
                      >
                      <span class="font-medium">{{ entry.name }}</span>
                    </div>
                  </td>
                  <td class="px-3 py-2 font-mono text-xs text-muted-foreground hidden md:table-cell">
                    {{ entry.uuid }}
                  </td>
                  <td class="px-3 py-2 text-right">
                    <button
                      type="button"
                      class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      :aria-label="t('players.remove')"
                      :title="t('players.remove')"
                      @click="onWhitelistRemove(entry)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </section>

    <!-- OPS -->
    <section
      v-if="tab === 'ops'"
      class="space-y-4"
    >
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <ShieldCheck
              :size="18"
              class="text-brand-500"
            />
            {{ t('players.ops.title') }}
          </CardTitle>
          <p class="text-xs text-muted-foreground mt-1">
            {{ t('players.ops.subtitle') }}
          </p>
        </CardHeader>
        <CardContent class="space-y-4">
          <form
            class="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end"
            @submit.prevent="onOpAdd"
          >
            <div class="space-y-1.5">
              <Label for="op-name">{{ t('players.ops.addLabel') }}</Label>
              <Input
                id="op-name"
                v-model="opName"
                :placeholder="t('players.ops.addPlaceholder')"
                autocomplete="off"
              />
            </div>
            <div class="space-y-1.5">
              <Label for="op-level">{{ t('players.ops.level') }}</Label>
              <select
                id="op-level"
                v-model.number="opLevel"
                class="h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option
                  v-for="lvl in [1, 2, 3, 4]"
                  :key="lvl"
                  :value="lvl"
                >
                  {{ lvl }}
                </option>
              </select>
            </div>
            <Button
              type="submit"
              :disabled="!opName.trim() || opsActions.add.isPending.value"
            >
              <Loader2
                v-if="opsActions.add.isPending.value"
                class="animate-spin"
              />
              <UserPlus v-else />
              {{ t('players.ops.add') }}
            </Button>
            <div class="flex items-center gap-2.5 sm:col-span-3">
              <Switch v-model="opBypass" />
              <Label class="text-xs">{{ t('players.ops.bypassLimit') }}</Label>
            </div>
            <p class="text-xs text-muted-foreground sm:col-span-3">
              {{ t('players.ops.levelHint') }}
            </p>
          </form>

          <div class="rounded-lg border border-border overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th class="px-3 py-2 text-left font-medium">
                    {{ t('players.headers.player') }}
                  </th>
                  <th class="w-24 px-3 py-2 text-left font-medium">
                    {{ t('players.headers.level') }}
                  </th>
                  <th class="w-32 px-3 py-2 text-left font-medium hidden sm:table-cell">
                    {{ t('players.headers.bypass') }}
                  </th>
                  <th class="px-3 py-2 text-left font-medium hidden md:table-cell">
                    {{ t('players.headers.uuid') }}
                  </th>
                  <th class="w-16 px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                <tr v-if="ops.isPending.value && !ops.data.value">
                  <td
                    colspan="5"
                    class="px-4 py-8 text-center text-muted-foreground"
                  >
                    {{ t('common.loading') }}
                  </td>
                </tr>
                <tr v-else-if="!ops.data.value?.length">
                  <td
                    colspan="5"
                    class="px-4 py-8 text-center text-muted-foreground"
                  >
                    {{ t('players.ops.empty') }}
                  </td>
                </tr>
                <tr
                  v-for="entry in ops.data.value ?? []"
                  :key="entry.uuid"
                  class="border-t border-border hover:bg-accent/30 transition-colors"
                >
                  <td class="px-3 py-2">
                    <div class="flex items-center gap-2.5">
                      <img
                        :src="`https://mc-heads.net/avatar/${entry.uuid}/24`"
                        :alt="entry.name"
                        class="size-6 rounded-md"
                        loading="lazy"
                      >
                      <span class="font-medium">{{ entry.name }}</span>
                    </div>
                  </td>
                  <td class="px-3 py-2">
                    <select
                      :value="entry.level"
                      class="h-7 rounded-md border border-input bg-background px-2 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      @change="onOpLevelChange(entry, Number(($event.target as HTMLSelectElement).value))"
                    >
                      <option
                        v-for="lvl in [1, 2, 3, 4]"
                        :key="lvl"
                        :value="lvl"
                      >
                        {{ lvl }}
                      </option>
                    </select>
                  </td>
                  <td class="px-3 py-2 hidden sm:table-cell">
                    <Switch
                      :model-value="entry.bypassesPlayerLimit"
                      @update:model-value="onOpBypassChange(entry, $event)"
                    />
                  </td>
                  <td class="px-3 py-2 font-mono text-xs text-muted-foreground hidden md:table-cell">
                    {{ entry.uuid }}
                  </td>
                  <td class="px-3 py-2 text-right">
                    <button
                      type="button"
                      class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      :aria-label="t('players.remove')"
                      :title="t('players.remove')"
                      @click="onOpRemove(entry)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </section>
  </div>
</template>
