<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowDown,
  ArrowUp,
  ChevronRight,
  Download,
  File as FileIcon,
  FolderPlus,
  Folder,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Upload as UploadIcon,
  X,
  Home,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  formatBytes,
  formatRelativeTime,
  useFileActions,
  useFileSelection,
  useFilesListing,
} from '@/composables/useFiles'
import { downloadAuthenticated, type FileEntry } from '@/lib/api'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const dialog = useDialogStore()

const path = computed<string>(() => (route.query.path as string) ?? '')
function navigate(p: string) {
  router.push({ query: { ...route.query, path: p || undefined } })
}

const listing = useFilesListing(path)
const selection = useFileSelection()
const actions = useFileActions(path)

watch(path, () => {
  selection.clear()
  searchQuery.value = ''
})

// ---------------------------------------------------------------------------
// Search + sort
// ---------------------------------------------------------------------------

type SortKey = 'name' | 'size' | 'modified'
const sortKey = ref<SortKey>('name')
const sortDir = ref<'asc' | 'desc'>('asc')
const searchQuery = ref('')

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

const visibleEntries = computed<FileEntry[]>(() => {
  const all = listing.data.value?.entries ?? []
  const q = searchQuery.value.trim().toLowerCase()
  const filtered = q ? all.filter((e) => e.name.toLowerCase().includes(q)) : all

  // Folders always come first regardless of sort key — that's the OS-level
  // expectation. Within each group we apply the chosen ordering.
  const sorter = (a: FileEntry, b: FileEntry): number => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    let cmp = 0
    switch (sortKey.value) {
      case 'name':
        cmp = a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
        break
      case 'size':
        cmp = (a.is_dir ? 0 : a.size) - (b.is_dir ? 0 : b.size)
        break
      case 'modified':
        cmp = (a.modified ?? 0) - (b.modified ?? 0)
        break
    }
    return sortDir.value === 'asc' ? cmp : -cmp
  }

  return [...filtered].sort(sorter)
})

interface Crumb { label: string; path: string }
const breadcrumbs = computed<Crumb[]>(() => {
  if (!path.value) return []
  const parts = path.value.split('/').filter(Boolean)
  const out: Crumb[] = []
  let acc = ''
  for (const part of parts) {
    acc = acc ? `${acc}/${part}` : part
    out.push({ label: part, path: acc })
  }
  return out
})

function joinPath(dir: string, name: string) {
  return dir ? `${dir.replace(/\/+$/, '')}/${name}` : name
}

function onRowClick(entry: FileEntry) {
  if (entry.is_dir) {
    navigate(joinPath(path.value, entry.name))
  } else {
    router.push({ path: '/files/edit', query: { path: joinPath(path.value, entry.name) } })
  }
}

function onDownload(entry: FileEntry) {
  const fullPath = joinPath(path.value, entry.name)
  downloadAuthenticated(`files/download/?path=${encodeURIComponent(fullPath)}`, entry.name)
}

async function onDeleteOne(entry: FileEntry) {
  const ok = await dialog.confirm({
    title: t('files.confirmDeleteOne', { name: entry.name }),
    confirmLabel: t('common.delete'),
    variant: 'destructive',
  })
  if (!ok) return
  actions.remove.mutate([joinPath(path.value, entry.name)])
}

async function onDeleteSelected() {
  const targets = selection.list.value.map((name) => joinPath(path.value, name))
  if (!targets.length) return
  const ok = await dialog.confirm({
    title: t('files.confirmDeleteMany', { n: targets.length }),
    confirmLabel: t('common.delete'),
    variant: 'destructive',
  })
  if (!ok) return
  actions.remove.mutate(targets)
  selection.clear()
}

const newFolderOpen = ref(false)
const newFolderName = ref('')
function onCreateFolder() {
  const name = newFolderName.value.trim()
  if (!name) return
  actions.mkdir.mutate(name, {
    onSuccess: () => {
      newFolderOpen.value = false
      newFolderName.value = ''
    },
  })
}

const uploadInput = ref<HTMLInputElement | null>(null)
function onUploadClick() {
  uploadInput.value?.click()
}
function onUploadFiles(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files || !input.files.length) return
  actions.upload.mutate(Array.from(input.files))
  input.value = ''
}

const dragging = ref(false)
let dragDepth = 0
function onDragEnter(e: DragEvent) {
  if (!e.dataTransfer?.types.includes('Files')) return
  dragDepth += 1
  dragging.value = true
}
function onDragLeave() {
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) dragging.value = false
}
function onDragOver(e: DragEvent) {
  if (e.dataTransfer?.types.includes('Files')) e.preventDefault()
}
function onDrop(e: DragEvent) {
  e.preventDefault()
  dragDepth = 0
  dragging.value = false
  const files = Array.from(e.dataTransfer?.files ?? [])
  if (files.length) actions.upload.mutate(files)
}

// Select-all targets only the *visible* (filtered) entries — selecting
// while a search is active should select what the user actually sees.
const allNames = computed(() => visibleEntries.value.map((e) => e.name))
const allSelected = computed(
  () => allNames.value.length > 0 && allNames.value.every((n) => selection.has(n)),
)
function toggleAll() {
  if (allSelected.value) selection.clear()
  else selection.setAll(allNames.value)
}

const displayPath = computed(() => `/${path.value || t('files.rootLabel')}`)
</script>

<template>
  <div
    class="relative space-y-4"
    @dragenter="onDragEnter"
    @dragleave="onDragLeave"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div class="space-y-1">
        <h2 class="text-2xl font-semibold tracking-tight">
          {{ t('files.title') }}
        </h2>
        <p class="text-sm text-muted-foreground">
          {{ t('files.subtitle') }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          :disabled="listing.isFetching.value"
          @click="actions.refresh()"
        >
          <RefreshCw :class="listing.isFetching.value ? 'animate-spin' : ''" />
          {{ t('common.refresh') }}
        </Button>
        <Button
          variant="outline"
          size="sm"
          @click="newFolderOpen = !newFolderOpen"
        >
          <FolderPlus />
          {{ t('files.newFolder') }}
        </Button>
        <Button
          size="sm"
          :disabled="actions.upload.isPending.value"
          @click="onUploadClick"
        >
          <Loader2
            v-if="actions.upload.isPending.value"
            class="animate-spin"
          />
          <UploadIcon v-else />
          {{ t('common.upload') }}
        </Button>
        <input
          ref="uploadInput"
          type="file"
          multiple
          class="hidden"
          @change="onUploadFiles"
        >
      </div>
    </header>

    <nav class="flex items-center gap-1 text-sm text-muted-foreground flex-wrap">
      <button
        type="button"
        class="inline-flex items-center gap-1 px-2 py-1 rounded-md hover:bg-accent hover:text-foreground transition-colors"
        :class="!path ? 'text-foreground font-medium' : ''"
        @click="navigate('')"
      >
        <Home :size="14" />
        <span>{{ t('files.rootLabel') }}</span>
      </button>
      <template
        v-for="(crumb, i) in breadcrumbs"
        :key="crumb.path"
      >
        <ChevronRight
          :size="14"
          class="text-muted-foreground/60"
        />
        <button
          type="button"
          class="px-2 py-1 rounded-md hover:bg-accent hover:text-foreground transition-colors"
          :class="i === breadcrumbs.length - 1 ? 'text-foreground font-medium' : ''"
          @click="navigate(crumb.path)"
        >
          {{ crumb.label }}
        </button>
      </template>
    </nav>

    <Transition name="view-fade">
      <form
        v-if="newFolderOpen"
        class="flex gap-2 items-center"
        @submit.prevent="onCreateFolder"
      >
        <Input
          v-model="newFolderName"
          :placeholder="t('files.newFolderName')"
          autofocus
          class="max-w-xs"
        />
        <Button
          type="submit"
          size="sm"
          :disabled="!newFolderName.trim() || actions.mkdir.isPending.value"
        >
          {{ t('common.create') }}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          @click="newFolderOpen = false; newFolderName = ''"
        >
          {{ t('common.cancel') }}
        </Button>
      </form>
    </Transition>

    <!-- Search bar + result count -->
    <div class="flex items-center gap-3">
      <div class="relative flex-1 max-w-md">
        <Search
          :size="14"
          class="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
        />
        <input
          v-model="searchQuery"
          type="search"
          :placeholder="t('files.searchPlaceholder')"
          class="h-9 w-full rounded-md border border-input bg-background pl-8 pr-8 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
        <button
          v-if="searchQuery"
          type="button"
          class="absolute right-1.5 top-1/2 -translate-y-1/2 inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:text-foreground"
          :aria-label="t('common.clear')"
          @click="searchQuery = ''"
        >
          <X :size="12" />
        </button>
      </div>
      <span
        v-if="searchQuery"
        class="text-xs text-muted-foreground tabular-nums"
      >
        {{ t('files.matchCount', { n: visibleEntries.length }) }}
      </span>
    </div>

    <Transition name="view-fade">
      <div
        v-if="selection.count.value > 0"
        class="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2.5"
      >
        <span class="text-sm font-medium">
          {{ t('common.selected', { n: selection.count.value }) }}
        </span>
        <span class="text-xs text-muted-foreground hidden sm:inline">
          {{ t('files.selectionInPath', { path: displayPath }) }}
        </span>
        <Button
          variant="ghost"
          size="sm"
          class="ml-auto"
          @click="selection.clear()"
        >
          <X />
          {{ t('common.clear') }}
        </Button>
        <Button
          variant="destructive"
          size="sm"
          :disabled="actions.remove.isPending.value"
          @click="onDeleteSelected"
        >
          <Loader2
            v-if="actions.remove.isPending.value"
            class="animate-spin"
          />
          <Trash2 v-else />
          {{ t('files.deleteSelected') }}
        </Button>
      </div>
    </Transition>

    <div class="rounded-xl border border-border bg-card overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th class="w-10 px-3 py-2 text-left">
              <input
                type="checkbox"
                :checked="allSelected"
                class="size-4 accent-primary cursor-pointer"
                :disabled="!allNames.length"
                @change="toggleAll"
              >
            </th>
            <th class="px-3 py-2 text-left font-medium">
              <button
                type="button"
                class="inline-flex items-center gap-1 hover:text-foreground transition-colors"
                @click="toggleSort('name')"
              >
                {{ t('common.name') }}
                <ArrowUp
                  v-if="sortKey === 'name' && sortDir === 'asc'"
                  :size="12"
                />
                <ArrowDown
                  v-else-if="sortKey === 'name' && sortDir === 'desc'"
                  :size="12"
                />
                <span
                  v-else
                  class="opacity-30 size-3 inline-block"
                />
              </button>
            </th>
            <th class="px-3 py-2 text-right font-medium hidden sm:table-cell">
              <button
                type="button"
                class="inline-flex items-center gap-1 hover:text-foreground transition-colors ml-auto"
                @click="toggleSort('size')"
              >
                {{ t('common.size') }}
                <ArrowUp
                  v-if="sortKey === 'size' && sortDir === 'asc'"
                  :size="12"
                />
                <ArrowDown
                  v-else-if="sortKey === 'size' && sortDir === 'desc'"
                  :size="12"
                />
                <span
                  v-else
                  class="opacity-30 size-3 inline-block"
                />
              </button>
            </th>
            <th class="px-3 py-2 text-right font-medium hidden md:table-cell">
              <button
                type="button"
                class="inline-flex items-center gap-1 hover:text-foreground transition-colors ml-auto"
                @click="toggleSort('modified')"
              >
                {{ t('common.modified') }}
                <ArrowUp
                  v-if="sortKey === 'modified' && sortDir === 'asc'"
                  :size="12"
                />
                <ArrowDown
                  v-else-if="sortKey === 'modified' && sortDir === 'desc'"
                  :size="12"
                />
                <span
                  v-else
                  class="opacity-30 size-3 inline-block"
                />
              </button>
            </th>
            <th class="w-24 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          <tr v-if="listing.isPending.value && !listing.data.value">
            <td
              colspan="5"
              class="px-4 py-8 text-center text-muted-foreground"
            >
              {{ t('common.loading') }}
            </td>
          </tr>
          <tr v-else-if="listing.isError.value">
            <td
              colspan="5"
              class="px-4 py-8 text-center text-destructive"
            >
              {{ listing.error.value?.message ?? t('files.loadFailed') }}
            </td>
          </tr>
          <tr v-else-if="!listing.data.value?.entries.length">
            <td
              colspan="5"
              class="px-4 py-12 text-center text-muted-foreground"
            >
              <div class="text-base font-medium mb-1">
                {{ t('files.emptyTitle') }}
              </div>
              <div class="text-xs">
                {{ t('files.emptySubtitle') }}
              </div>
            </td>
          </tr>
          <tr v-else-if="!visibleEntries.length">
            <td
              colspan="5"
              class="px-4 py-8 text-center text-muted-foreground"
            >
              <div class="text-sm">
                {{ t('files.noMatch', { q: searchQuery }) }}
              </div>
            </td>
          </tr>
          <tr
            v-for="entry in visibleEntries"
            :key="entry.name"
            class="border-t border-border hover:bg-accent/40 transition-colors"
            :class="{ 'bg-accent/40': selection.has(entry.name) }"
          >
            <td class="px-3 py-2">
              <input
                type="checkbox"
                :checked="selection.has(entry.name)"
                class="size-4 accent-primary cursor-pointer"
                @click.stop
                @change="selection.toggle(entry.name)"
              >
            </td>
            <td
              class="px-3 py-2 cursor-pointer"
              @click="onRowClick(entry)"
            >
              <div class="flex items-center gap-2.5 min-w-0">
                <Folder
                  v-if="entry.is_dir"
                  :size="16"
                  class="text-brand-500 shrink-0"
                />
                <FileIcon
                  v-else
                  :size="16"
                  class="text-muted-foreground shrink-0"
                />
                <span
                  class="truncate"
                  :class="entry.is_dir ? 'font-medium' : ''"
                >
                  {{ entry.name }}
                </span>
              </div>
            </td>
            <td class="px-3 py-2 text-right tabular-nums text-muted-foreground hidden sm:table-cell">
              {{ entry.is_dir ? t('common.none') : formatBytes(entry.size) }}
            </td>
            <td class="px-3 py-2 text-right text-muted-foreground hidden md:table-cell">
              {{ formatRelativeTime(entry.modified) }}
            </td>
            <td class="px-3 py-2">
              <div class="flex items-center justify-end gap-1">
                <button
                  v-if="!entry.is_dir"
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                  :aria-label="t('common.download')"
                  :title="t('common.download')"
                  @click.stop="onDownload(entry)"
                >
                  <Download :size="14" />
                </button>
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                  :aria-label="t('common.delete')"
                  :title="t('common.delete')"
                  @click.stop="onDeleteOne(entry)"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <Transition name="view-fade">
      <div
        v-if="dragging"
        class="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm"
      >
        <div class="rounded-2xl border-2 border-dashed border-brand-500 bg-card/80 px-12 py-10 text-center shadow-2xl">
          <UploadIcon
            :size="32"
            class="mx-auto text-brand-500 mb-3"
          />
          <div class="text-base font-semibold tracking-tight mb-1">
            {{ t('files.dropToUpload') }}
          </div>
          <div class="text-sm text-muted-foreground">
            {{ t('files.dropTarget', { path: displayPath }) }}
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
