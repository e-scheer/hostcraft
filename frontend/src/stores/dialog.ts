import { defineStore } from 'pinia'
import { ref } from 'vue'

export type DialogChoice = 'confirm' | 'cancel' | 'alternative'

export interface ConfirmOptions {
  title: string
  description?: string
  /** Override the default "Confirm" button label. */
  confirmLabel?: string
  /** Override the default "Cancel" button label. */
  cancelLabel?: string
  /** "destructive" gives a red primary button (delete/discard flows). */
  variant?: 'default' | 'destructive'
  /** Optional third button between Cancel and Confirm. When set, ``ask()``
   * resolves to ``'alternative'`` if the user clicks it. ``confirm()`` still
   * returns a boolean — the alternative resolves to ``false`` there. */
  alternativeLabel?: string
  /** Visual style for the alternative button. Defaults to ``outline``. */
  alternativeVariant?: 'default' | 'destructive' | 'outline' | 'ghost'
}

export const useDialogStore = defineStore('dialog', () => {
  const open = ref(false)
  const options = ref<ConfirmOptions>({ title: '' })

  let resolver: ((value: DialogChoice) => void) | null = null

  function ask(opts: ConfirmOptions): Promise<DialogChoice> {
    resolver?.('cancel')
    options.value = opts
    open.value = true
    return new Promise<DialogChoice>((resolve) => {
      resolver = resolve
    })
  }

  async function confirm(opts: ConfirmOptions): Promise<boolean> {
    return (await ask(opts)) === 'confirm'
  }

  function answer(value: DialogChoice) {
    open.value = false
    const r = resolver
    resolver = null
    r?.(value)
  }

  return { open, options, ask, confirm, answer }
})
