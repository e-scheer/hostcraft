<script setup lang="ts">
import { Toaster } from '@/components/ui/sonner'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
</script>

<template>
  <RouterView />
  <Toaster />
  <ConfirmDialog />
</template>
