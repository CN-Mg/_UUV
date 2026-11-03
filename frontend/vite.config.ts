import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8010', '/assets': 'http://127.0.0.1:8010',
      '/ws': { target: 'ws://127.0.0.1:8010', ws: true },
    },
  },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
