<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Button } from '@/components/ui/button'
import { useDialogStore } from '@/stores/dialog'

const { t } = useI18n()
const dialog = useDialogStore()

function onKey(e: KeyboardEvent) {
  if (!dialog.open) return
  if (e.key === 'Escape') {
    e.preventDefault()
    dialog.answer('cancel')
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    dialog.answer('confirm')
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

// Lock body scroll while the modal is open.
watch(
  () => dialog.open,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
  },
)
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-overlay">
      <div
        v-if="dialog.open"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        role="dialog"
        aria-modal="true"
        @click.self="dialog.answer('cancel')"
      >
        <Transition name="modal-card" appear>
          <div
            v-if="dialog.open"
            class="w-full max-w-sm rounded-xl border border-border bg-card shadow-2xl p-6 space-y-4"
          >
            <div class="space-y-1.5">
              <h3 class="text-base font-semibold tracking-tight">
                {{ dialog.options.title }}
              </h3>
              <p
                v-if="dialog.options.description"
                class="text-sm text-muted-foreground leading-relaxed"
              >
                {{ dialog.options.description }}
              </p>
            </div>
            <div class="flex flex-wrap justify-end gap-2 pt-2">
              <Button variant="ghost" size="sm" @click="dialog.answer('cancel')">
                {{ dialog.options.cancelLabel ?? t('common.cancel') }}
              </Button>
              <Button
                v-if="dialog.options.alternativeLabel"
                :variant="dialog.options.alternativeVariant ?? 'outline'"
                size="sm"
                @click="dialog.answer('alternative')"
              >
                {{ dialog.options.alternativeLabel }}
              </Button>
              <Button
                :variant="dialog.options.variant === 'destructive' ? 'destructive' : 'default'"
                size="sm"
                autofocus
                @click="dialog.answer('confirm')"
              >
                {{ dialog.options.confirmLabel ?? t('common.confirm') }}
              </Button>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<!-- modal-overlay/modal-card transitions live in src/styles/animations.css -->
