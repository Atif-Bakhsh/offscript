import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
    watch: { ignored: ['**/playwright-report/**', '**/test-results/**'] },
  },
  test: {
    environment: 'jsdom', setupFiles: ['src/__tests__/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'], restoreMocks: true,
  },
})
