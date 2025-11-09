import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proxy /api calls to FastAPI on :8088
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8088',
        changeOrigin: true,
      },
    },
  },
})
