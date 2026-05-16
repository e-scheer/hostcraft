import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    // File watching over Docker bind mounts is unreliable without polling on
    // some hosts. Slightly higher CPU, much more reliable HMR.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      // In Docker dev VITE_BACKEND_URL is set to http://backend:8000 (internal
       // network). The localhost fallback is only hit if you run Vite outside
       // Docker — keep it in sync with HOSTCRAFT_BACKEND_HOST_PORT.
      '/api': {
        target: process.env.VITE_BACKEND_URL ?? 'http://localhost:8001',
        changeOrigin: true,
      },
      '/ws': {
        target: (process.env.VITE_BACKEND_URL ?? 'http://localhost:8001').replace(
          /^http/,
          'ws',
        ),
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1024,
  },
})
