<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { ArrowDownToLine, Check, Copy, Eraser, SendHorizontal, Terminal as TerminalIcon } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { useConsole } from '@/composables/useConsole'
import { applySuggestion, suggestionsFor, type Suggestion } from '@/lib/mc-commands'

const { t } = useI18n()

const wrapper = useTemplateRef<HTMLDivElement>('wrapper')
const terminalEl = useTemplateRef<HTMLDivElement>('terminalEl')
const inputEl = useTemplateRef<HTMLInputElement>('inputEl')

const cmd = ref('')

const {
  connected,
  mount,
  observe,
  send,
  historyPrev,
  historyNext,
  clear,
  scrollToBottom,
  bufferText,
} = useConsole()

const copied = ref(false)
async function copyContents() {
  const text = bufferText()
  if (!text) {
    toast.error(t('console.copyEmpty'))
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    toast.success(t('console.copied', { lines: text.split('\n').length }))
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    toast.error(t('common.downloadFailed'))
  }
}

onMounted(async () => {
  await nextTick()
  if (terminalEl.value) mount(terminalEl.value)
  if (wrapper.value) observe(wrapper.value)
})

// --- Autocomplete ---------------------------------------------------------
// Static, client-side. We don't ask the MC server for completions — that
// would cost an RCON round-trip per keystroke. The catalog in
// ``lib/mc-commands.ts`` covers vanilla + Paper, which is what 95 % of
// commands typed here will hit.
const suggestions = computed<Suggestion[]>(() => suggestionsFor(cmd.value))
const activeIdx = ref(0)
const suggestionsOpen = ref(true) // hidden after Escape; reopens on next change
watch(suggestions, () => { activeIdx.value = 0 })
watch(cmd, () => { suggestionsOpen.value = true })

const showSuggestions = computed(
  () => suggestionsOpen.value && suggestions.value.length > 0,
)

function accept(idx = activeIdx.value) {
  const sug = suggestions.value[idx]
  if (!sug) return
  cmd.value = applySuggestion(cmd.value, sug)
  suggestionsOpen.value = false
  nextTick(() => {
    inputEl.value?.focus()
    inputEl.value?.setSelectionRange(cmd.value.length, cmd.value.length)
  })
}

function onSubmit() {
  if (!cmd.value.trim()) return
  send(cmd.value)
  cmd.value = ''
}

function onUp(e: KeyboardEvent) {
  e.preventDefault()
  // While the suggestion list is open we navigate it; arrow keys for
  // history only kick in once it's dismissed.
  if (showSuggestions.value) {
    activeIdx.value =
      (activeIdx.value - 1 + suggestions.value.length) % suggestions.value.length
    return
  }
  cmd.value = historyPrev(cmd.value)
  nextTick(() => inputEl.value?.setSelectionRange(cmd.value.length, cmd.value.length))
}

function onDown(e: KeyboardEvent) {
  e.preventDefault()
  if (showSuggestions.value) {
    activeIdx.value = (activeIdx.value + 1) % suggestions.value.length
    return
  }
  cmd.value = historyNext()
  nextTick(() => inputEl.value?.setSelectionRange(cmd.value.length, cmd.value.length))
}

function onTab(e: KeyboardEvent) {
  if (!showSuggestions.value) return
  e.preventDefault()
  accept()
}

function onEsc() {
  if (showSuggestions.value) suggestionsOpen.value = false
}
</script>

<template>
  <div
    ref="wrapper"
    class="flex flex-col h-[calc(100vh-7rem)] gap-3"
  >
    <header class="flex items-center gap-3">
      <h2 class="text-2xl font-semibold tracking-tight flex items-center gap-2">
        <TerminalIcon
          :size="22"
          class="text-brand-500"
        />
        {{ t('console.title') }}
      </h2>
      <span
        class="inline-flex items-center gap-1.5 rounded-full bg-card border border-border px-2.5 py-0.5 text-xs font-medium"
      >
        <span
          class="size-1.5 rounded-full"
          :class="
            connected
              ? 'bg-brand-500 shadow-[0_0_10px_var(--brand-500)]'
              : 'bg-muted-foreground/60'
          "
        />
        {{ connected ? t('console.connected') : t('console.disconnected') }}
      </span>
      <div class="ml-auto flex items-center gap-1">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors rounded-md px-2 py-1"
          :title="t('console.scrollToBottomHint')"
          @click="scrollToBottom()"
        >
          <ArrowDownToLine :size="14" />
          {{ t('console.scrollToBottom') }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors rounded-md px-2 py-1"
          :title="t('console.copyHint')"
          @click="copyContents"
        >
          <Check
            v-if="copied"
            :size="14"
            class="text-emerald-500"
          />
          <Copy
            v-else
            :size="14"
          />
          {{ copied ? t('console.copiedShort') : t('console.copy') }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors rounded-md px-2 py-1"
          @click="clear()"
        >
          <Eraser :size="14" />
          {{ t('console.clear') }}
        </button>
      </div>
    </header>

    <div
      ref="terminalEl"
      class="flex-1 min-h-0 rounded-xl border border-border bg-[#0a0a0a] p-3 overflow-hidden"
    />

    <form
      class="flex items-center gap-2 shrink-0 relative"
      @submit.prevent="onSubmit"
    >
      <!-- Suggestion popover — floats just above the input so the eye
           stays where it was when picking a completion. -->
      <ul
        v-if="showSuggestions"
        class="absolute bottom-full left-6 right-0 mb-2 max-h-64 overflow-auto rounded-md border border-border bg-card shadow-2xl py-1 text-sm font-mono z-30"
      >
        <li
          v-for="(s, i) in suggestions"
          :key="s.label + i"
          class="px-3 py-1.5 cursor-pointer flex items-baseline gap-3"
          :class="i === activeIdx ? 'bg-accent text-foreground' : 'hover:bg-accent/40'"
          @mousedown.prevent="accept(i)"
          @mouseenter="activeIdx = i"
        >
          <span class="text-brand-500 shrink-0">{{ s.label }}</span>
          <span class="text-xs text-muted-foreground truncate font-sans">
            {{ s.description }}
          </span>
        </li>
        <li class="px-3 py-1 text-[10px] text-muted-foreground/70 italic font-sans border-t border-border mt-1">
          {{ t('console.autocompleteHint') }}
        </li>
      </ul>

      <span class="font-mono text-brand-500 select-none">$</span>
      <input
        ref="inputEl"
        v-model="cmd"
        :disabled="!connected"
        class="flex-1 h-10 rounded-md bg-card border border-border px-3 font-mono text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background disabled:opacity-50"
        :placeholder="t('console.placeholder')"
        autocomplete="off"
        spellcheck="false"
        @keydown.up="onUp"
        @keydown.down="onDown"
        @keydown.tab="onTab"
        @keydown.esc="onEsc"
      >
      <Button
        type="submit"
        :disabled="!connected || !cmd.trim()"
      >
        <SendHorizontal />
        {{ t('console.send') }}
      </Button>
    </form>
  </div>
</template>
