// Vite build/dev configuration.
//
// The dev server proxies /api to the backend so the browser always talks to a
// single origin — exactly as nginx does in production. That keeps CORS out of
// the picture and lets the SameSite=Strict refresh cookie (SPEC §6.2) work the
// same way in development as it does in production.

import path from 'node:path'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API_TARGET = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: API_TARGET, changeOrigin: true },
      // WebSocket endpoint for live alerts and scan progress (SPEC §7).
      '/ws': { target: API_TARGET, ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split the heaviest libraries out of the main bundle so a change to
        // application code does not invalidate the vendor chunk in the cache.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
})
