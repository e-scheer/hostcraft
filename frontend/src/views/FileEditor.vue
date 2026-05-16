<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery } from '@tanstack/vue-query'
import { HTTPError } from 'ky'
import { ArrowLeft, Download, Loader2, Save } from 'lucide-vue-next'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { downloadAuthenticated, extractErrorMessage, filesApi } from '@/lib/api'
import { useThemeStore } from '@/stores/theme'
import { useDialogStore } from '@/stores/dialog'
import '@/lib/monaco-setup'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
const dialog = useDialogStore()

const filePath = computed(() => (route.query.path as string) ?? '')
const fileName = computed(() => filePath.value.split('/').pop() ?? '')

const language = computed(() => detectLanguage(fileName.value))
const monacoTheme = computed(() => (theme.theme === 'dark' ? 'vs-dark' : 'vs'))

const content = ref('')
const initialContent = ref('')
const isDirty = computed(() => content.value !== initialContent.value)

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

const fileQuery = useQuery({
  queryKey: ['files', 'read', filePath] as const,
  queryFn: () => filesApi.read(filePath.value),
  enabled: computed(() => Boolean(filePath.value)),
  retry: false,
  staleTime: 0,
  gcTime: 0,
})

watch(
  () => fileQuery.data.value,
  (data) => {
    if (data) {
      content.value = data.content
      initialContent.value = data.content
    }
  },
  { immediate: true },
)

const errorStatus = computed(() => {
  const err = fileQuery.error.value
  if (err instanceof HTTPError) return err.response.status
  return null
})

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

const save = useMutation({
  mutationFn: () => filesApi.write(filePath.value, content.value),
  onSuccess: () => {
    initialContent.value = content.value
    toast.success(t('fileEditor.saved'))
  },
  onError: async (err) => {
    toast.error(t('fileEditor.saveFailed'), { description: await extractErrorMessage(err) })
  },
})

function trySave() {
  if (!isDirty.value || save.isPending.value) return
  save.mutate()
}

// Wire Ctrl+S / Cmd+S inside Monaco AND globally on the page.
function onMonacoMount(editor: any, monaco: any) {
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, trySave)
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault()
    trySave()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

// ---------------------------------------------------------------------------
// Navigation guards
// ---------------------------------------------------------------------------

function goBack() {
  // Strip the trailing file segment to land back in its directory.
  const dir = filePath.value.includes('/')
    ? filePath.value.slice(0, filePath.value.lastIndexOf('/'))
    : ''
  router.push({ path: '/files', query: { path: dir || undefined } })
}

onBeforeRouteLeave(async () => {
  if (!isDirty.value) return true
  const ok = await dialog.confirm({
    title: t('common.unsavedTitle'),
    description: t('fileEditor.unsavedConfirm'),
    confirmLabel: t('common.discard'),
    variant: 'destructive',
  })
  return ok
})

function onDownload() {
  downloadAuthenticated(
    `files/download/?path=${encodeURIComponent(filePath.value)}`,
    fileName.value || 'file',
  )
}

const editorOptions = {
  fontFamily: '"JetBrains Mono", ui-monospace, monospace',
  fontSize: 13,
  lineHeight: 1.5,
  minimap: { enabled: false },
  smoothScrolling: true,
  scrollBeyondLastLine: false,
  renderWhitespace: 'selection' as const,
  automaticLayout: true,
  padding: { top: 12, bottom: 12 },
  tabSize: 2,
  wordWrap: 'on' as const,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const LANG_BY_EXT: Record<string, string> = {
  json: 'json', json5: 'json', mcmeta: 'json',
  yaml: 'yaml', yml: 'yaml',
  properties: 'ini', ini: 'ini', cfg: 'ini', conf: 'ini', toml: 'ini',
  txt: 'plaintext', log: 'plaintext',
  md: 'markdown', markdown: 'markdown',
  xml: 'xml', html: 'html', htm: 'html', svg: 'xml',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  css: 'css', scss: 'scss', less: 'less',
  sh: 'shell', bash: 'shell', zsh: 'shell',
  py: 'python',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  java: 'java',
  kt: 'kotlin',
  sql: 'sql',
}

function detectLanguage(name: string): string {
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
  return LANG_BY_EXT[ext] ?? 'plaintext'
}
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-7rem)] gap-3">
    <!-- Toolbar -->
    <header class="flex items-center gap-2 flex-wrap">
      <Button variant="ghost" size="sm" @click="goBack">
        <ArrowLeft />
        {{ t('fileEditor.back') }}
      </Button>
      <h2 class="text-lg font-semibold tracking-tight font-mono truncate min-w-0">
        {{ filePath || '—' }}
      </h2>
      <Transition name="view-fade">
        <span
          v-if="isDirty"
          class="inline-flex items-center gap-1.5 rounded-full bg-amber-400/10 text-amber-300 px-2.5 py-0.5 text-xs font-medium"
        >
          <span class="size-1.5 rounded-full bg-amber-400 animate-pulse" />
          {{ t('fileEditor.unsaved') }}
        </span>
      </Transition>

      <span class="ml-auto hidden md:inline text-[11px] text-muted-foreground font-mono">
        {{ t('fileEditor.shortcutSave') }}
      </span>
      <Button
        :disabled="!isDirty || save.isPending.value || fileQuery.isPending.value || errorStatus !== null"
        @click="trySave"
      >
        <Loader2 v-if="save.isPending.value" class="animate-spin" />
        <Save v-else />
        {{ save.isPending.value ? t('fileEditor.saving') : t('fileEditor.save') }}
      </Button>
    </header>

    <!-- Body -->
    <div class="flex-1 min-h-0 rounded-xl border border-border bg-card overflow-hidden relative">
      <!-- Loading -->
      <div
        v-if="fileQuery.isPending.value"
        class="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground"
      >
        <Loader2 class="animate-spin mr-2" :size="14" />
        {{ t('fileEditor.loading') }}
      </div>

      <!-- Error states -->
      <div
        v-else-if="errorStatus !== null"
        class="absolute inset-0 flex flex-col items-center justify-center text-center px-6 gap-3"
      >
        <h3 class="text-base font-semibold">
          {{
            errorStatus === 415
              ? t('fileEditor.binaryHeading')
              : errorStatus === 413
                ? t('fileEditor.tooLargeHeading')
                : t('fileEditor.loadFailed')
          }}
        </h3>
        <p class="text-sm text-muted-foreground max-w-md">
          {{
            errorStatus === 415
              ? t('fileEditor.binaryDescription')
              : errorStatus === 413
                ? t('fileEditor.tooLargeDescription')
                : (fileQuery.error.value?.message ?? '')
          }}
        </p>
        <div class="flex gap-2 mt-2">
          <Button variant="outline" @click="goBack">
            <ArrowLeft />
            {{ t('fileEditor.back') }}
          </Button>
          <Button v-if="errorStatus === 415 || errorStatus === 413" @click="onDownload">
            <Download />
            {{ t('common.download') }}
          </Button>
        </div>
      </div>

      <!-- Editor -->
      <VueMonacoEditor
        v-else
        v-model:value="content"
        :language="language"
        :theme="monacoTheme"
        :options="editorOptions"
        class="absolute inset-0"
        @mount="onMonacoMount"
      />
    </div>
  </div>
</template>
