<script setup lang="ts">
import { Toaster as Sonner } from 'vue-sonner'
</script>

<template>
  <Sonner
    class="toaster group"
    position="bottom-right"
    :toast-options="{
      classes: {
        toast:
          'group toast group-[.toaster]:bg-card group-[.toaster]:text-card-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
        description: 'group-[.toast]:text-muted-foreground',
        actionButton: 'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
        cancelButton: 'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
      },
    }"
  />
</template>
