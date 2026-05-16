<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  modelValue?: string | number
  type?: string
  placeholder?: string
  disabled?: boolean
  class?: string
}>()

defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<template>
  <input
    :type="type ?? 'text'"
    :value="modelValue"
    :placeholder="placeholder"
    :disabled="disabled"
    :class="cn(
      'flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors',
      'placeholder:text-muted-foreground',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background',
      'disabled:cursor-not-allowed disabled:opacity-50',
      'file:border-0 file:bg-transparent file:text-sm file:font-medium',
      $props.class,
    )"
    @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
  >
</template>
