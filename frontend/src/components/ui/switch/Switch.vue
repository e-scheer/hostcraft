<script setup lang="ts">
import { SwitchRoot, SwitchThumb } from 'reka-ui'
import { cn } from '@/lib/utils'

defineProps<{
  modelValue?: boolean
  disabled?: boolean
  class?: string
}>()

defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <SwitchRoot
    :model-value="modelValue"
    :disabled="disabled"
    :class="cn(
      'inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-colors',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background',
      'data-[state=checked]:bg-primary data-[state=unchecked]:bg-muted',
      'disabled:cursor-not-allowed disabled:opacity-50',
      $props.class,
    )"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <SwitchThumb
      class="block size-4 rounded-full bg-background shadow-md ring-0 transition-transform data-[state=checked]:translate-x-[18px] data-[state=unchecked]:translate-x-0.5"
    />
  </SwitchRoot>
</template>
